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
    Formatter,
    Handler,
    Logger,
    LogRecord,
    StreamHandler,
    basicConfig,
    getLogger,
)
from typing import IO, TYPE_CHECKING, Any, Literal, TypeVar
from unittest.mock import patch

import click
from click.types import IntRange

from . import Choice, Context, Parameter
from .colorize import default_theme
from .parameters import ExtraOption, search_params

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable, Sequence


class LogLevel(IntEnum):
    """Mapping of :ref:`canonical log level names <levels>` to their integer level.

    That's our own version of `logging._nameToLevel
    <https://github.com/python/cpython/blob/a379749/Lib/logging/__init__.py#L115-L124>`_,
    but:

    - sorted from lowest to highest verbosity,
    - excludes the following levels:
        - :data:`WARNING <logging.NOTSET>`, which is considered internal
        - ``WARN``, which :meth:`is obsolete <logging.Logger.warning>`
        - ``FATAL``, which `shouldn't be used <https://github.com/python/cpython/issues/85013>`_
          and has been `replaced by CRITICAL
          <https://github.com/python/cpython/blob/8597be46135a0f4a53e99dade67724bbb8e3c1c9/Lib/logging/__init__.py#L2148-L2152>`_
    """

    CRITICAL = logging.CRITICAL
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    INFO = logging.INFO
    DEBUG = logging.DEBUG


DEFAULT_LEVEL: LogLevel = LogLevel.WARNING
""":data:`WARNING <logging.WARNING>` is the default level we expect any loggers to starts their lives at.

:data:`WARNING <logging.WARNING>` has been chosen as it is `the level at which the default Python's
global root logger is set up <https://github.com/python/cpython/blob/0df7c3a/Lib/logging/__init__.py#L1945>`_.

This value is also used as the default level for :class:`VerbosityOption` .
"""


TFormatter = TypeVar("TFormatter", bound=Formatter)
THandler = TypeVar("THandler", bound=Handler)
"""Custom types to be used in type hints below."""


class ExtraStreamHandler(StreamHandler):
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
        <https://github.com/python/cpython/blob/eed7865ceea83f56e46307c9dc78cb53526071f6/Lib/logging/__init__.py#L1128>`_.

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
            msg = self.format(record)
            click.echo(msg, err=self._stderr_output)
        except RecursionError:
            raise

        # If exception occurs, dump the traceback to stderr.
        except Exception:
            self.handleError(record)


class ExtraFormatter(Formatter):
    """Click Extra's default log formatter."""

    def formatMessage(self, record: LogRecord) -> str:
        """Colorize the record's log level name before calling the standard
        formatter.

        Colors are sourced from a :class:`click_extra.colorize.HelpExtraTheme`. Default
        colors are configured on :const:`click_extra.colorize.default_theme`.
        """
        level = record.levelname.lower()
        level_style = getattr(default_theme, level, None)
        if level_style:
            record.levelname = level_style(level)
        return super().formatMessage(record)


def extraBasicConfig(
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
    stream_handler_class: type[THandler] = (
        # XXX This funky code format is a workaround for autopep8 unstable long-line
        # wrapping.
        ExtraStreamHandler  # type: ignore[assignment]
    ),
    file_handler_class: type[THandler] = FileHandler,  # type: ignore[assignment]
    formatter_class: type[TFormatter] = ExtraFormatter,  # type: ignore[assignment]
) -> None:
    """Configure the global ``root`` logger.

    This function is a wrapper around Python standard library's :func:`logging.basicConfig`,
    but with additional parameters and tweaked defaults.

    It sets up the global ``root`` logger, and optionally adds a file or stream handler to it.

    Differences in default values:

    ==========  ================================  ======================================
    Argument    :func:`extraBasicConfig` default  :func:`logging.basicConfig` default
    ==========  ================================  ======================================
    ``style``   ``{``                             ``%``
    ``format``  ``{levelname}: {message}``        ``%(levelname)s:%(name)s:%(message)s``
    ==========  ================================  ======================================

    This function takes the same parameters as :func:`logging.basicConfig`, but require them
    to be all passed as explicit keywords arguments.

    :param filename: Specifies that a :class:`logging.FileHandler` be created, using the
        specified filename, rather than an :py:class:`ExtraStreamHandler`.
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
        :py:class:`ExtraStreamHandler`. Note that this argument is incompatible with
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
        :py:class:`ExtraStreamHandler`.
    :param file_handler_class: A :py:class:`logging.Handler` class that will be used in
        :func:`logging.basicConfig` to create a default file-based handler. Defaults to
        :py:class:`FileHandler`.
    :param formatter_class: A :py:class:`logging.Formatter` class of the formatter that
        will be used in :func:`logging.basicConfig` to setup the default formatter. Defaults to
        :py:class:`ExtraFormatter`.

    .. note::
        I don't like the camel-cased name of this function and would have called it
        ``extra_basic_config()``, but it's kept this way for consistency with Python's
        standard library.
    """
    # Collect all arguments that are not None, because basicConfig is testing the
    # presence of them instead of their values. So we'll add them conditionally to
    # kwargs.
    kwargs = {}
    for arg_id in inspect.signature(extraBasicConfig).parameters:
        if arg_id in locals() and locals()[arg_id] is not None:
            kwargs[arg_id] = locals()[arg_id]

    call_str = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
    getLogger("click_extra").debug(f"Call basicConfig({call_str})")

    # Consume along the way each kwargs' parameter not recognized by basicConfig.
    with patch.object(logging, "StreamHandler", kwargs.pop("stream_handler_class")):
        with patch.object(logging, "FileHandler", kwargs.pop("file_handler_class")):
            with patch.object(logging, "Formatter", kwargs.pop("formatter_class")):
                basicConfig(**kwargs)


def new_extra_logger(
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
    - Attach a new :py:class:`ExtraStreamHandler` with :py:class:`ExtraFormatter`,
    - Return the logger object.

    This function is a wrapper around :func:`extraBasicConfig` and takes the same keywords arguments.

    :param name: ID of the logger to setup. If ``None``, Python's ``root``
        logger will be used. If a logger with the provided name is not found in the
        global registry, a new logger with that name will be created.
    :param propagate: Sets the logger's :attr:`propagate <logging.Logger.propagate>` attribute. Defaults to ``False``.
    :param force: Same as the *force* parameter from :func:`logging.basicConfig` and :func:`extraBasicConfig`. Defaults to ``True``.
    :param kwargs: Any other keyword parameters supported by :func:`logging.basicConfig` and :func:`extraBasicConfig`.
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
        extraBasicConfig(force=force, **kwargs)

    return logger


class ExtraVerbosity(ExtraOption):
    """A base class implementing all the common halpers to manipulated logger's
    verbosity.

    Sets the level of the provided logger. If no logger is provided, sets the level of
    the global ``root`` logger.

    .. important::
        The internal ``click_extra`` logger will be aligned to the level set through
        this class.

    .. caution::
        This class is not intended to be used as-is. It is an internal place to
        reconcile the verbosity level selected by the competing logger options
        implemented below:

        - ``--verbosity``
        - ``--verbose``/``-v``
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
            getLogger("click_extra").debug(f"Reset {logger} to {DEFAULT_LEVEL.name}.")
            logger.setLevel(DEFAULT_LEVEL.value)
            # new_extra_logger(name=logger.name)

    def set_level(self, ctx: Context, param: Parameter, level: LogLevel) -> None:
        """Set level of all loggers configured on the option.

        All verbosity-related options are attached to this callback, so that's where we
        reconcile the multiple values provided by different options. In case of a
        conflict, the highest versbosity level always takes precedence.

        The final reconciled level chosen for the logger will be saved in
        ``ctx.meta["click_extra.verbosity_level"]``. This context property served as a
        kind of global state shared by all verbosity-related options.
        """
        # Skip setting the level if another option has already sets it or is at an equal
        # or lower level.
        current_level = ctx.meta.get("click_extra.verbosity_level")
        if current_level and current_level <= level:
            return

        ctx.meta["click_extra.verbosity_level"] = level

        for logger in self.all_loggers:
            logger.setLevel(level.value)
            getLogger("click_extra").debug(f"Set {logger} to {level.name}.")

        ctx.call_on_close(self.reset_loggers)

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
            Otherwise, we will create a new logger with :func:`new_extra_logger`
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
            logger = new_extra_logger(name=default_logger)
            self.logger_name = logger.name

        kwargs.setdefault("callback", self.set_level)

        super().__init__(
            param_decls=param_decls,
            expose_value=expose_value,
            is_eager=is_eager,
            **kwargs,
        )


class VerbosityOption(ExtraVerbosity):
    """``--verbosity`` option to set the the log level of :class:`ExtraVerbosity`."""

    def set_level(self, ctx: Context, param: Parameter, value: LogLevel) -> None:
        """The value passed to ``--verbosity`` will be saved in
        ``ctx.meta["click_extra.verbosity"]``.
        """
        ctx.meta["click_extra.verbosity"] = value
        super().set_level(ctx, param, value)

    def __init__(
        self,
        param_decls: Sequence[str] | None = None,
        default_logger: Logger | str = logging.root.name,
        default: LogLevel = DEFAULT_LEVEL,
        metavar="LEVEL",
        type=Choice(LogLevel, case_sensitive=False),
        # type=Choice(LogLevel),
        help=_("Either {log_levels}.").format(
            log_levels=", ".join(LogLevel.__members__)
        ),
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


class VerboseOption(ExtraVerbosity):
    """``--verbose``/``-v``` option to increase the log level of :class:`ExtraVerbosity`
    by a number of steps.

    If ``-v`` is passed to a CLI, then it will increase the verbosity level by one
    step. The option can be provided multiple times by the user. So if ``-vv`` (or
    `-v -v`) is passed, the verbosity will be increase by 2 levels.

    The default base-level from which we start incrementing is sourced from
    :attr:`VerbosityOption.default`. So with ``--verbosity``'s default set to
    ``WARNING``:

    - ``-v`` will increase the level to ``INFO``,
    - ``-vv`` will increase the level to ``DEBUG``,
    - any number of repetition above that point will be set to the maximum level, so for
      ``-vvvvv`` for example will be capped at ``DEBUG``.
    """

    def get_base_level(self, ctx: Context) -> LogLevel:
        """Returns the default base-level from which the option will start incrementing.

        We try first to get the default level from any instance of
        :class:`VerbosityOption` defined on the current command. If none is found, it's
        because the ``--verbose`` option is used standalone. In which case we defaults to
        :const:`DEFAULT_LEVEL`.
        """
        verbosity_option = search_params(
            ctx.command.params, VerbosityOption, include_subclasses=False
        )
        return (
            verbosity_option.default  # type: ignore[union-attr, return-value]
            if verbosity_option
            else DEFAULT_LEVEL
        )

    def get_help_record(self, ctx: Context) -> tuple[str, str] | None:
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
                    f"Increase the default {self.get_base_level(ctx).name} verbosity "
                    "by one level for each additional repetition of the option."
                ),
            )

        with help_message_patch:
            return super().get_help_record(ctx)

    def set_level(self, ctx: Context, param: Parameter, value: int) -> None:
        """Translate the number of steps to the target log level.

        The value passed to ``--verbose``/``-v`` will be saved in
        ``ctx.meta["click_extra.verbose"]``.
        """
        ctx.meta["click_extra.verbose"] = value

        # No -v option has been called, skip meddling with log levels.
        if value == 0:
            return

        levels_rank = tuple(LogLevel)
        base_level = self.get_base_level(ctx)
        default_level_index = levels_rank.index(base_level)

        # Cap new index to the last, verbosier level.
        new_level_index = min(default_level_index + value, len(levels_rank) - 1)
        new_level = levels_rank[new_level_index]

        super().set_level(ctx, param, new_level)

        # Print the message after effectively altering the log level so we have a chance
        # to see it at DEBUG-level.
        getLogger("click_extra").debug(
            f"Increased log verbosity by {value} levels: "
            f"from {base_level.name} to {new_level.name}."
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
