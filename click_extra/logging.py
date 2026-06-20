# Copyright Kevin Deldycke <kevin@deldycke.com> and contributors.
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
"""Logging utilities."""

from __future__ import annotations

import inspect
import logging
import sys
from contextlib import nullcontext
from enum import IntEnum
from gettext import gettext as _
from logging import (
    FileHandler,
    Handler,
    Logger,
    getLogger,
)
from unittest.mock import patch

import click
from click.types import IntRange

from . import EnumChoice, context
from .parameters import ExtraOption, search_params
from .theme import get_current_theme

TYPE_CHECKING = False
if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Sequence
    from logging import LogRecord
    from typing import IO, Any, Literal


class LogLevel(IntEnum):
    """Mapping of :ref:`canonical log level names <levels>` to their integer level.

    That's our own version of `logging._nameToLevel
    <https://github.com/python/cpython/blob/3.14/Lib/logging/__init__.py#L115-L124>`_,
    but:

    - sorted from lowest to highest verbosity,
    - excludes the following levels:
        - :data:`NOTSET <logging.NOTSET>`, which is considered internal
        - ``WARN``, which :meth:`is obsolete <logging.Logger.warning>`
        - ``FATAL``, which `shouldn't be used <https://github.com/python/cpython/issues/85013>`_
          and has been `replaced by CRITICAL
          <https://github.com/python/cpython/blob/3.14/Lib/logging/__init__.py#L2150-L2154>`_
    """

    CRITICAL = logging.CRITICAL
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    INFO = logging.INFO
    DEBUG = logging.DEBUG

    def __str__(self):
        """Use upper-case names as string representation."""
        return self.name


DEFAULT_LEVEL: LogLevel = LogLevel.WARNING
""":data:`WARNING <logging.WARNING>` is the default level we expect any loggers to starts their lives at.

:data:`WARNING <logging.WARNING>` has been chosen as it is `the level at which the default Python's
global root logger is set up <https://github.com/python/cpython/blob/3.14/Lib/logging/__init__.py#L1997>`_.

This value is also used as the default level for :class:`VerbosityOption` .
"""


_RESET_REGISTERED: str = f"{context.META_NAMESPACE}_verbosity_reset_registered"
"""Internal sentinel marking that ``reset_loggers`` was queued on the context.

Lives in ``ctx.meta`` so the verbosity inheritance chain
(``_VerbosityOption`` / ``VerbosityOption`` / ``VerboseOption`` / ``QuietOption``)
registers the close callback at most once per invocation, even when several
verbosity options are passed.
"""


_COUNTER_SCANNED: str = f"{context.META_NAMESPACE}_verbosity_counter_scanned"
"""Internal sentinel marking that the ``-v``/``-q`` counter was pre-resolved.

The first verbosity option reaching :meth:`_VerbosityOption.handle_parse_result`
reads the raw ``--verbose``/``--quiet`` repetition counts from the parsed
``opts`` and stashes them on the context before any option applies a level. This
way the option that fires first already reconciles the full counter and never
applies an intermediate, louder level that a later ``-q`` would have to lower
(which would leak its ``Set ... DEBUG`` debug trace).
"""


def _last_param(
    ctx: click.Context, klass: type[click.Parameter]
) -> click.Parameter | None:
    """Return the last parameter of exactly ``klass`` on the command, or ``None``.

    Tolerates duplicates: when an option is declared more than once (e.g. an explicit
    ``@verbosity_option`` stacked on a Click Extra command that already ships one),
    Click keeps the last occurrence, so we mirror that here instead of erroring out on
    the ambiguity.
    """
    options = search_params(
        ctx.command.params, klass, include_subclasses=False, unique=False
    )
    return options[-1] if options else None  # type: ignore[index]


class StreamHandler(logging.StreamHandler):
    """A handler to output logs to the console.

    Wraps :class:`logging.StreamHandler`, but use :func:`click.echo` to support color printing.

    Only :py:data:`<stderr> <sys.stderr>` or :py:data:`<stdout> <sys.stdout>` are allowed as output stream.

    If stream is not specified, :py:data:`<stderr> <sys.stderr>` is used by default
    """

    _stderr_output: bool = True
    """:func:`click.echo`'s ``err`` parameter to be used at printing time."""

    _stream: IO[Any] = sys.stderr

    @property
    def stream(self) -> IO[Any]:
        """The stream to which logs are written.

        A proxy of the parent :class:`logging.StreamHandler`'s `stream attribute
        <https://github.com/python/cpython/blob/3.14/Lib/logging/__init__.py#L1129>`_.

        Redefined here to enforce checks on the stream value.
        """
        return self._stream

    @stream.setter
    def stream(self, stream: IO[Any]) -> None:
        if stream not in (sys.stderr, sys.stdout):
            raise ValueError("Only <stderr> or <stdout> are allowed as output stream.")

        self._stream = stream

        # Sync click.echo()'s err parameter with the target stream.
        self._stderr_output = stream == sys.stderr

    def emit(self, record: LogRecord) -> None:
        """Use :func:`click.echo` to print to the console."""
        try:
            click.echo(self.format(record), err=self._stderr_output)
        except RecursionError:
            raise

        # If exception occurs, dump the traceback to stderr.
        except Exception:  # noqa: BLE001
            self.handleError(record)


class Formatter(logging.Formatter):
    """Click Extra's default log formatter."""

    def formatMessage(self, record: LogRecord) -> str:
        """Colorize the record's log level name before calling the standard
        formatter.

        Colors are sourced from a :class:`click_extra.theme.HelpTheme`,
        resolved per-invocation via :func:`click_extra.theme.get_current_theme`.
        """
        level = record.levelname.lower()
        level_style = getattr(get_current_theme(), level, None)
        if level_style:
            record.levelname = level_style(level)
        return super().formatMessage(record)


def basicConfig(
    *,
    # Arguments from Python's standard library's basicConfig:
    filename: str | None = None,
    filemode: str = "a",
    format: str | None = "{levelname}: {message}",
    datefmt: str | None = None,
    style: Literal["%", "{", "$"] = "{",
    level: int | str | None = None,
    stream: IO[Any] | None = None,
    handlers: Iterable[Handler] | None = None,
    force: bool = False,
    encoding: str | None = None,
    errors: str | None = "backslashreplace",
    # New arguments specific to this function:
    stream_handler_class: type[Handler] = StreamHandler,
    file_handler_class: type[Handler] = FileHandler,
    formatter_class: type[logging.Formatter] = Formatter,
) -> None:
    """Configure the global ``root`` logger.

    This function is a wrapper around Python standard library's :func:`logging.basicConfig`,
    but with additional parameters and tweaked defaults.

    It sets up the global ``root`` logger, and optionally adds a file or stream handler to it.

    Differences in default values:

    ==========  ===========================  ======================================
    Argument    :func:`basicConfig` default  :func:`logging.basicConfig` default
    ==========  ===========================  ======================================
    ``style``   ``{``                        ``%``
    ``format``  ``{levelname}: {message}``   ``%(levelname)s:%(name)s:%(message)s``
    ==========  ===========================  ======================================

    This function takes the same parameters as :func:`logging.basicConfig`, but require them
    to be all passed as explicit keywords arguments.

    :param filename: Specifies that a :class:`logging.FileHandler` be created, using the
        specified filename, rather than an :py:class:`StreamHandler`.
    :param filemode: If *filename* is specified, open the file in this :func:`mode <.open>`.

        Defaults to ``a``.
    :param format: Use the specified format string for the handler.

        Defaults to ``{levelname}: {message}``.
    :param datefmt: Use the specified date/time format, as accepted by
        :func:`time.strftime`.
    :param style: If format is specified, use this style for the format string:

        - ``%`` for :ref:`printf-style <old-string-formatting>`,
        - ``{`` for :meth:`str.format`,
        - ``$`` for :class:`string.Template`.

        Defaults to ``{``.
    :param level: Set the ``root`` logger level to the specified :ref:`level <levels>`.
    :param stream: Use the specified stream to initialize the
        :py:class:`StreamHandler`. Note that this argument is incompatible with
        *filename* - if both are present, a ``ValueError`` is raised.
    :param handlers: If specified, this should be an iterable of already created
        handlers to add to the ``root`` logger. Any handlers which don't already have a
        formatter set will be assigned the default formatter created in this function.
        Note that this argument is incompatible with *filename* or *stream* - if both
        are present, a ``ValueError`` is raised.
    :param force: If this argument is specified as ``True``, any existing
        handlers attached to the ``root`` logger are removed and closed, before carrying
        out the configuration as specified by the other arguments.
    :param encoding: :ref:`Name of the encoding <standard-encodings>` used to decode or
        encode the file. To be specified along with *filename*, and passed to
        :class:`logging.FileHandler` for opening the output file.
    :param errors: Optional string that specifies :ref:`how encoding and decoding errors
        are to be handled <error-handlers>` by the :class:`logging.FileHandler`. Defaults
        to ``backslashreplace``. Note that if ``None`` is specified, it will be passed as
        such to :func:`open`.

    .. important::
        Always keep the signature of this function, the default values of its
        parameters and its documentation in sync with the one from Python's standard
        library.

    These new arguments are available for better configurability:

    :param stream_handler_class: A :py:class:`logging.Handler` class that will be used in
        :func:`logging.basicConfig` to create a default stream-based handler. Defaults to
        :py:class:`StreamHandler`.
    :param file_handler_class: A :py:class:`logging.Handler` class that will be used in
        :func:`logging.basicConfig` to create a default file-based handler. Defaults to
        :py:class:`FileHandler`.
    :param formatter_class: A :py:class:`logging.Formatter` class of the formatter that
        will be used in :func:`logging.basicConfig` to setup the default formatter. Defaults to
        :py:class:`Formatter`.

    .. note::
        I don't like the camel-cased name of this function and would have called it
        ``basic_config()``, but it's kept this way for consistency with Python's
        standard library :func:`logging.basicConfig`.
    """
    # Collect all arguments that are not None, because basicConfig is testing the
    # presence of them instead of their values. So we'll add them conditionally to
    # kwargs.
    kwargs = {}
    for arg_id in inspect.signature(basicConfig).parameters:
        if arg_id in locals() and locals()[arg_id] is not None:
            kwargs[arg_id] = locals()[arg_id]

    call_str = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
    getLogger("click_extra").debug(f"Call basicConfig({call_str})")

    # Consume along the way each kwargs' parameter not recognized by basicConfig.
    with (
        patch.object(logging, "StreamHandler", kwargs.pop("stream_handler_class")),
        patch.object(logging, "FileHandler", kwargs.pop("file_handler_class")),
        patch.object(logging, "Formatter", kwargs.pop("formatter_class")),
    ):
        logging.basicConfig(**kwargs)


def new_logger(
    name: str = logging.root.name,
    *,
    propagate: bool = False,
    force: bool = True,
    **kwargs,
) -> Logger:
    """Setup a logger in the style of Click Extra.

    By default, this helper will:

    - :func:`Fetch the logger <logging.getLogger>` registered under the ``name`` parameter, or creates a new one
      with that name if it doesn't exist,
    - Set the logger's :attr:`propagate <logging.Logger.propagate>` attribute to ``False``,
    - Force removal of any existing handlers and formatters attached to the logger,
    - Attach a new :py:class:`StreamHandler` with :py:class:`Formatter`,
    - Return the logger object.

    This function is a wrapper around :func:`basicConfig` and takes the same keywords arguments.

    :param name: ID of the logger to setup. If ``None``, Python's ``root``
        logger will be used. If a logger with the provided name is not found in the
        global registry, a new logger with that name will be created.
    :param propagate: Sets the logger's :attr:`propagate <logging.Logger.propagate>` attribute. Defaults to ``False``.
    :param force: Same as the *force* parameter from :func:`logging.basicConfig` and :func:`basicConfig`. Defaults to ``True``.
    :param kwargs: Any other keyword parameters supported by :func:`logging.basicConfig` and :func:`basicConfig`.
    """
    if name == logging.root.name:
        logger = logging.root
        root_logger_patch = nullcontext()

    else:
        logger = getLogger(name)  # type: ignore[assignment]
        logger.propagate = propagate
        root_logger_patch = patch.object(  # type: ignore[assignment]
            logging,
            "root",
            logger,
        )

    with root_logger_patch:
        basicConfig(force=force, **kwargs)

    return logger


class _VerbosityOption(ExtraOption):
    """A base class implementing all the common helpers to manipulated logger's
    verbosity.

    Sets the level of the provided logger. If no logger is provided, sets the level of
    the global ``root`` logger.

    .. important::
        The internal ``click_extra`` logger will be aligned to the level set through
        this class.

    .. caution::
        This class is not intended to be used as-is. It is the internal place where
        the level requested by the three competing options is reconciled:

        - ``--verbosity LEVEL`` sets an absolute level (defaults to
          :const:`DEFAULT_LEVEL`).
        - ``--verbose``/``-v`` raises the verbosity, one :class:`LogLevel` step per
          repetition.
        - ``--quiet``/``-q`` lowers the verbosity, one :class:`LogLevel` step per
          repetition.

        ``-v`` and ``-q`` form a single signed counter around the base level:
        ``net = (number of -v) - (number of -q)``. The counter is clamped to the
        :class:`LogLevel` range, so it never reaches past :attr:`LogLevel.DEBUG`
        (loudest) nor :attr:`LogLevel.CRITICAL` (quietest). See
        :meth:`resolve_level` for the way the counter is reconciled with an explicit
        ``--verbosity``.

    .. note::
        ``-q`` only lowers the *logging* verbosity. It deliberately does not silence
        :func:`click.echo`: a command's primary output is not a diagnostic and stays
        on its stream.

    .. todo::
        Let the counter reach beyond the current :class:`LogLevel` range, as sketched
        by the ``-vvvv`` (trace) and ``-q`` (silence everything) notes that used to
        live here:

        - a ``TRACE`` pseudo-level below :attr:`LogLevel.DEBUG` (numeric value ``5``,
          mirroring ``logging.DEBUG - 5``) so repeated ``-v`` can surface
          finer-grained tracing past ``DEBUG``;
        - a ``SILENT`` pseudo-level above :attr:`LogLevel.CRITICAL` (any value above
          ``logging.CRITICAL``) so repeated ``-q`` can suppress every record,
          including :attr:`LogLevel.CRITICAL`.

        Both require extending :class:`LogLevel`, which ripples into the
        ``--verbosity`` :class:`~click_extra.types.EnumChoice`, the
        :class:`Formatter` level-name color lookup and the level-ordering tests.
        They are intentionally left out of the symmetric-counter change that
        introduced ``-q``, where the counter simply clamps at ``DEBUG``/``CRITICAL``.
    """

    logger_name: str
    """The ID of the logger to set the level to.

    This will be provided to :func:`logging.getLogger` to fetch the logger object, and
    as such, can be a dot-separated string to build hierarchical loggers.
    """

    @property
    def all_loggers(self) -> Generator[Logger, None, None]:
        """Returns the list of logger IDs affected by the verbosity option.

        Will returns ``click_extra`` internal logger first, then the option's
        :attr:`logger_name`.
        """
        for name in ("click_extra", self.logger_name):
            yield getLogger(name)

    def reset_loggers(self) -> None:
        """Forces all loggers managed by the option to be reset to
        :const:`DEFAULT_LEVEL`.

        .. important::
            Loggers are reset in reverse order to ensure the internal logger is changed
            last. That way the internal ``click_extra`` logger can report its ongoing
            logger-altering operations while using the logging facilities itself.

        .. danger::
            Resetting loggers is extremely important for unittests. Because they're
            global, loggers have tendency to leak and pollute their state between
            multiple test calls.
        """
        for logger in list(self.all_loggers)[::-1]:
            getLogger("click_extra").debug(f"Reset {logger} to {DEFAULT_LEVEL}.")
            logger.setLevel(DEFAULT_LEVEL.value)
            # new_logger(name=logger.name)

    def handle_parse_result(self, ctx, opts, args):
        """Pre-resolve the ``-v``/``-q`` counter before any level is applied.

        The first verbosity option to be processed reads the raw ``--verbose`` and
        ``--quiet`` repetition counts straight from the parsed ``opts`` and stashes them
        on the context. By the time any verbosity callback applies a level,
        :meth:`resolve_level` already sees the full counter, so the option that fires
        first lands on the final level directly instead of applying a louder
        intermediate that a later ``-q`` would have to walk back. See
        :data:`_COUNTER_SCANNED`.
        """
        if not ctx.resilient_parsing and not context.get(ctx, _COUNTER_SCANNED):
            context.set(ctx, _COUNTER_SCANNED, True)
            for klass, key in (
                (VerboseOption, context.VERBOSE),
                (QuietOption, context.QUIET),
            ):
                option = _last_param(ctx, klass)
                if option is not None:
                    value, _ = option.consume_value(ctx, opts)
                    context.set(ctx, key, value)

        return super().handle_parse_result(ctx, opts, args)

    def get_base_level(self, ctx: click.Context) -> LogLevel:
        """Returns the base level the ``-v``/``-q`` counter is anchored at.

        Sourced from the :attr:`~VerbosityOption.default` of any
        :class:`VerbosityOption` declared on the current command. When the
        ``-v``/``-q`` options are used standalone (no ``--verbosity``), it defaults to
        :const:`DEFAULT_LEVEL`.
        """
        verbosity_option = _last_param(ctx, VerbosityOption)
        if verbosity_option is None:
            return DEFAULT_LEVEL
        return verbosity_option.default  # type: ignore[return-value]

    def resolve_level(self, ctx: click.Context) -> LogLevel:
        """Reconcile ``--verbosity``, ``-v`` and ``-q`` into a single level.

        Reads the raw value each option recorded on the context
        (:data:`~click_extra.context.VERBOSITY`,
        :data:`~click_extra.context.VERBOSE` and
        :data:`~click_extra.context.QUIET`) and folds them with this rule:

        - ``net = verbose - quiet``;
        - ``net == 0``: the ``--verbosity`` value wins (its default when the user did
          not pass it);
        - ``net > 0``: the more verbose of the counter result and the ``--verbosity``
          value wins;
        - ``net < 0``: the more quiet of the counter result and the ``--verbosity``
          value wins.

        The counter starts from :meth:`get_base_level` and is clamped to the
        :class:`LogLevel` range. This keeps ``-v`` backward compatible (it still counts
        up from the default and the loudest request wins), while letting ``-q`` mirror
        it downwards.
        """
        base = self.get_base_level(ctx)
        verbosity: LogLevel = context.get(ctx, context.VERBOSITY, base)
        net: int = context.get(ctx, context.VERBOSE, 0) - context.get(
            ctx, context.QUIET, 0
        )

        if net == 0:
            return verbosity

        levels = tuple(LogLevel)
        # Higher index == more verbose. ``-v`` raises the index, ``-q`` lowers it.
        counter_index = min(max(levels.index(base) + net, 0), len(levels) - 1)
        counter = levels[counter_index]

        # ``min`` picks the more verbose (lowest numeric) level, ``max`` the quieter.
        return min(counter, verbosity) if net > 0 else max(counter, verbosity)

    def apply_verbosity(self, ctx: click.Context) -> None:
        """Reconcile the requested verbosity and apply it to all managed loggers.

        Called by every verbosity option after it has recorded its own raw value, so
        the last option to fire reconciles the complete picture via
        :meth:`resolve_level`. The reconciled level is published on ``ctx.meta`` under
        :data:`~click_extra.context.VERBOSITY_LEVEL` and only (re)applied when it
        actually changes, to keep the debug trace free of redundant ``Set`` lines.
        """
        # Skip logger reconfiguration during help rendering, shell completion,
        # and any ``make_context(resilient_parsing=True)`` path.
        if ctx.resilient_parsing:
            return

        new_level = self.resolve_level(ctx)

        # Idempotent: several verbosity options flow through here, so without this
        # guard the same level would be re-applied and re-logged once per option.
        if context.get(ctx, context.VERBOSITY_LEVEL) == new_level:
            return

        context.set(ctx, context.VERBOSITY_LEVEL, new_level)

        for logger in self.all_loggers:
            logger.setLevel(new_level.value)
            getLogger("click_extra").debug(f"Set {logger} to {new_level}.")

        # Register the close callback at most once per ctx. All verbosity options flow
        # through this method, so without a guard the same ``reset_loggers`` would be
        # queued more than once on Context._close_callbacks.
        if not context.get(ctx, _RESET_REGISTERED):
            ctx.call_on_close(self.reset_loggers)
            context.set(ctx, _RESET_REGISTERED, True)

    def set_level(self, ctx: click.Context, param: click.Parameter, value: Any) -> None:
        """Base callback: subclasses record their raw value first, then reconcile.

        The base implementation only triggers reconciliation. Each subclass overrides
        it to stash its own raw value on the context before delegating here.
        """
        self.apply_verbosity(ctx)

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        default_logger: Logger | str = logging.root.name,
        expose_value=False,
        is_eager=True,
        **kwargs,
    ) -> None:
        """Set up a verbosity-altering option.

        :param default_logger: If a :class:`logging.Logger` object is provided, that's
            the instance to which we will set the level to. If the parameter is a string
            and is found in the global registry, we will use it as the logger's ID.
            Otherwise, we will create a new logger with :func:`new_logger`
            Default to the global ``root`` logger.
        """
        # A logger object has been provided, fetch its name.
        if isinstance(default_logger, Logger):
            self.logger_name = default_logger.name
        # Use the provided string if it is found in the registry.
        elif default_logger in Logger.manager.loggerDict:
            self.logger_name = default_logger
        # Create a new logger with Click Extra's default configuration.
        # XXX That's also the case in which the root logger will fall into, because as
        # a special case, it is not registered in Logger.manager.loggerDict.
        else:
            logger = new_logger(name=default_logger)
            self.logger_name = logger.name

        kwargs.setdefault("callback", self.set_level)

        super().__init__(
            param_decls=param_decls,
            expose_value=expose_value,
            is_eager=is_eager,
            **kwargs,
        )


class VerbosityOption(_VerbosityOption):
    """``--verbosity LEVEL`` option to set the log level of :class:`_VerbosityOption`."""

    def set_level(
        self, ctx: click.Context, param: click.Parameter, value: LogLevel
    ) -> None:
        """Record the ``--verbosity`` value, then reconcile.

        The value passed to ``--verbosity`` is saved in
        ``ctx.meta[click_extra.context.VERBOSITY]``.
        """
        context.set(ctx, context.VERBOSITY, value)
        self.apply_verbosity(ctx)

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        default_logger: Logger | str = logging.root.name,
        default: LogLevel = DEFAULT_LEVEL,
        metavar="LEVEL",
        type=EnumChoice(LogLevel),
        help=_("Either {log_levels}.").format(log_levels=", ".join(map(str, LogLevel))),
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--verbosity",)

        super().__init__(
            param_decls=param_decls,
            default_logger=default_logger,
            default=default,
            metavar=metavar,
            type=type,
            help=help,
            **kwargs,
        )


class VerboseOption(_VerbosityOption):
    """``--verbose``/``-v`` option to raise the log level of :class:`_VerbosityOption` by
    one step per repetition.

    Each ``-v`` raises the verbosity by one :class:`LogLevel` step. The option can be
    repeated, so ``-vv`` (or ``-v -v``) raises it by two steps.

    The base level the counter starts from is sourced from
    :attr:`VerbosityOption.default`. So with ``--verbosity``'s default left at
    ``WARNING``:

    - ``-v`` raises the level to ``INFO``,
    - ``-vv`` raises the level to ``DEBUG``,
    - any further repetition is clamped at the loudest level, so ``-vvvvv`` for example
      resolves to ``DEBUG``.

    ``-v`` shares a single signed counter with :class:`QuietOption`'s ``-q``, so the two
    cancel out: ``-v -q`` leaves the level unchanged. See
    :meth:`_VerbosityOption.resolve_level` for the full reconciliation rule with
    ``--verbosity``.
    """

    def get_help_record(self, ctx: click.Context) -> tuple[str, str] | None:
        """Dynamiccaly generates the default help message.

        We need that patch because :meth:`get_base_level` depends on the context, so we
        cannot hard-code the help message as :meth:`VerboseOption.__init__` default.
        """
        help_message_patch = nullcontext()
        if self.help is None:
            help_message_patch = patch.object(  # type:ignore[assignment]
                self,
                "help",
                (
                    f"Increase the default {self.get_base_level(ctx)} verbosity "
                    "by one level for each additional repetition of the option."
                ),
            )

        with help_message_patch:
            return super().get_help_record(ctx)

    def set_level(self, ctx: click.Context, param: click.Parameter, value: int) -> None:
        """Record the ``-v`` repetition count, then reconcile.

        The number of repetitions is saved in
        ``ctx.meta[click_extra.context.VERBOSE]`` and folded into the verbosity
        counter by :meth:`_VerbosityOption.resolve_level`.
        """
        context.set(ctx, context.VERBOSE, value)
        self.apply_verbosity(ctx)

        # Report the net effect after the level has been applied, so the message has a
        # chance to be seen at DEBUG level.
        if value and not ctx.resilient_parsing:
            getLogger("click_extra").debug(
                f"Increased log verbosity by {value} levels: "
                f"from {self.get_base_level(ctx)} "
                f"to {context.get(ctx, context.VERBOSITY_LEVEL)}."
            )

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        count: bool = True,
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--verbose", "-v")

        # Force type and default to have them aligned with the counting option's
        # original behavior:
        # https://github.com/pallets/click/blob/5dd6288/src/click/core.py#L2612-L2618
        kwargs["type"] = IntRange(min=0)
        kwargs["default"] = 0

        super().__init__(
            param_decls=param_decls,
            count=count,
            **kwargs,
        )


class QuietOption(_VerbosityOption):
    """``--quiet``/``-q`` option to lower the log level of :class:`_VerbosityOption` by
    one step per repetition.

    The symmetric counterpart of :class:`VerboseOption`: where ``-v`` raises the
    verbosity one :class:`LogLevel` step at a time, ``-q`` lowers it. Starting from
    :attr:`VerbosityOption.default` (``WARNING`` by default):

    - ``-q`` lowers the level to ``ERROR``,
    - ``-qq`` lowers the level to ``CRITICAL``,
    - any further repetition is clamped at the quietest level, so ``-qqqqq`` for example
      resolves to ``CRITICAL``.

    ``-q`` shares a single signed counter with :class:`VerboseOption`'s ``-v``, so the
    two cancel out: ``-v -q`` leaves the level unchanged. See
    :meth:`_VerbosityOption.resolve_level` for the full reconciliation rule with
    ``--verbosity``.
    """

    def get_help_record(self, ctx: click.Context) -> tuple[str, str] | None:
        """Dynamiccaly generates the default help message.

        We need that patch because :meth:`get_base_level` depends on the context, so we
        cannot hard-code the help message as :meth:`QuietOption.__init__` default.
        """
        help_message_patch = nullcontext()
        if self.help is None:
            help_message_patch = patch.object(  # type:ignore[assignment]
                self,
                "help",
                (
                    f"Decrease the default {self.get_base_level(ctx)} verbosity "
                    "by one level for each additional repetition of the option."
                ),
            )

        with help_message_patch:
            return super().get_help_record(ctx)

    def set_level(self, ctx: click.Context, param: click.Parameter, value: int) -> None:
        """Record the ``-q`` repetition count, then reconcile.

        The number of repetitions is saved in
        ``ctx.meta[click_extra.context.QUIET]`` and folded into the verbosity counter
        by :meth:`_VerbosityOption.resolve_level`.
        """
        context.set(ctx, context.QUIET, value)
        self.apply_verbosity(ctx)

        # Report the net effect after the level has been applied, so the message has a
        # chance to be seen at DEBUG level.
        if value and not ctx.resilient_parsing:
            getLogger("click_extra").debug(
                f"Decreased log verbosity by {value} levels: "
                f"from {self.get_base_level(ctx)} "
                f"to {context.get(ctx, context.VERBOSITY_LEVEL)}."
            )

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        count: bool = True,
        **kwargs,
    ) -> None:
        if not param_decls:
            param_decls = ("--quiet", "-q")

        # Force type and default to mirror the counting behavior of VerboseOption.
        kwargs["type"] = IntRange(min=0)
        kwargs["default"] = 0

        super().__init__(
            param_decls=param_decls,
            count=count,
            **kwargs,
        )
