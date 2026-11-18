#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.15"
# ///
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
"""Record `tests/tachyon-live.cast`, the stream Tachyon's live mode writes.

Tachyon, the sampling profiler of Python 3.15 (`python -m profiling.sampling`),
draws its `--live` mode with curses, as a full-screen program. This script runs
that interface under a pseudo-terminal sized like the screenshots of the Python
documentation, and keeps every chunk it writes with the time it arrived, as an
[asciicast v2](https://docs.asciinema.org/manual/asciicast/v2/) file.
`tests/test_recording.py` replays the file into the animated capture it pins.

The interface is fed synthetic samples of a made-up bakery program instead of a
real process. No process memory is read, so no privilege is needed: on macOS,
profiling a live process takes `sudo`. Run it with:

```shell-session
$ uv run --script tests/tachyon_cast.py
```

The samples come from a seeded generator, but the refreshes follow the wall
clock, so two recordings never come out byte for byte the same.
"""

from __future__ import annotations

import codecs
import fcntl
import json
import opcode
import os
import pty
import random
import select
import struct
import subprocess
import sys
import termios
import time
from collections import namedtuple
from pathlib import Path

CAST = Path(__file__).with_name("tachyon-live.cast")
"""Where the recording is written."""

COLUMNS = 120
"""Width of the terminal, that of the screenshots in the Python documentation.

Tachyon draws their second `%` column from 120 columns on, and their missing
`cumtime` column only from 140.
"""

ROWS = 47
"""Height of the terminal, that of the same screenshots.

Their table shows 34 rows, and Tachyon gives it the height less 13.
"""

LIVE_SECONDS = 4.0
"""Seconds of live profiling, the length of the documentation's own loop."""

FINISHED_SECONDS = 1.0
"""Seconds the final screen stays up once profiling ends, before quitting."""

RATE = 10_000
"""Samples fed per second, Tachyon's sampling rate in the documentation."""

LocationInfo = namedtuple("LocationInfo", "lineno end_lineno col_offset end_col_offset")
FrameInfo = namedtuple("FrameInfo", "filename location funcname opcode")
ThreadInfo = namedtuple("ThreadInfo", "thread_id frame_info status")
InterpreterInfo = namedtuple("InterpreterInfo", "interpreter_id threads")


def frame(location: str, funcname: str, name: str | None = None) -> FrameInfo:
    """One frame of a sampled stack.

    :param location: file and line, as `path:line`.
    :param funcname: the function's qualified name.
    :param name: the instruction executing, for the top frame only.
    """
    filename, lineno = location.rsplit(":", 1)
    number = None
    if name:
        # Specialized instructions, like `CALL_BUILTIN_O`, have no public table.
        specialized = getattr(opcode, "_specialized_opmap", {})
        number = specialized.get(name, opcode.opmap.get(name))
    line = int(lineno)
    return FrameInfo(filename, LocationInfo(line, line, -1, -1), funcname, number)


def bakery() -> dict[int, list[tuple[float, list[FrameInfo], int]]]:
    """The stacks each thread of the bakery samples on, weighted.

    :return: by thread, each stack with its weight and its thread status.
    """
    # Imported here: the package ships with Python 3.15, and the documentation
    # build reads this module on older versions too.
    from profiling.sampling.constants import (
        THREAD_STATUS_GIL_REQUESTED,
        THREAD_STATUS_HAS_GIL,
        THREAD_STATUS_MAIN_THREAD,
        THREAD_STATUS_ON_CPU,
    )

    main = frame("bakery/__main__.py:12", "main")
    orders = frame("bakery/kitchen.py:73", "Kitchen.run_orders")
    batch = frame("bakery/oven.py:142", "Oven.bake_batch")
    worker = frame("threading.py:1012", "Thread.run")
    running = THREAD_STATUS_MAIN_THREAD | THREAD_STATUS_HAS_GIL | THREAD_STATUS_ON_CPU
    resting = THREAD_STATUS_MAIN_THREAD
    return {
        1: [
            (
                440,
                [
                    frame("bakery/dough.py:88", "proof_dough", "CALL_BUILTIN_O"),
                    orders,
                    main,
                ],
                resting,
            ),
            (
                1,
                [frame("bakery/dough.py:88", "proof_dough", "CALL"), orders, main],
                resting,
            ),
            (
                200,
                [
                    frame("bakery/oven.py:177", "Oven.wait_for_heat", "CALL"),
                    batch,
                    orders,
                    main,
                ],
                resting,
            ),
            (
                110,
                [
                    frame(
                        "bakery/oven.py:516",
                        "Oven.rotate_trays",
                        "LOAD_ATTR_INSTANCE_VALUE",
                    ),
                    batch,
                    orders,
                    main,
                ],
                running,
            ),
            (
                52,
                [frame("bakery/timers.py:25", "wait_for_timer", "CALL"), orders, main],
                resting,
            ),
            (
                38,
                [
                    frame("selectors.py:398", "_PollLikeSelector.select", "CALL"),
                    frame("bakery/till.py:91", "Till.serve"),
                    main,
                ],
                resting,
            ),
            (
                18,
                [
                    frame("bakery/dough.py:41", "knead", "BINARY_OP_MULTIPLY_INT"),
                    batch,
                    orders,
                    main,
                ],
                running,
            ),
            (
                12,
                [
                    frame("bakery/dough.py:47", "knead", "FOR_ITER_RANGE"),
                    batch,
                    orders,
                    main,
                ],
                running,
            ),
            (
                12,
                [
                    frame("bakery/dough.py:49", "knead", "BINARY_OP_ADD_INT"),
                    batch,
                    orders,
                    main,
                ],
                running,
            ),
            (
                9,
                [
                    frame(
                        "bakery/oven.py:434", "Oven.bake.<locals>.glaze", "STORE_ATTR"
                    ),
                    batch,
                    orders,
                    main,
                ],
                running,
            ),
            (
                4,
                [
                    frame("bakery/proofer.py:774", "Proofer.wait_for_rise", "CALL"),
                    orders,
                    main,
                ],
                resting,
            ),
            (
                3,
                [
                    frame("bakery/proofer.py:795", "Proofer.wait_for_timeout", "CALL"),
                    orders,
                    main,
                ],
                resting,
            ),
            (
                3,
                [
                    frame("subprocess.py:2040", "Popen._try_wait", "CALL"),
                    frame("bakery/till.py:120", "Till.print_receipt"),
                    main,
                ],
                resting,
            ),
            (
                2,
                [
                    frame("~:0", "<GC>"),
                    frame("bakery/pantry.py:677", "Pantry.count_jars"),
                    orders,
                    main,
                ],
                running,
            ),
            (
                2,
                [
                    frame("bakery/recipe.py:68", "Recipe.scale", "FOR_ITER_LIST"),
                    orders,
                    main,
                ],
                running,
            ),
            (
                1,
                [
                    frame(
                        "bakery/pantry.py:1453",
                        "Pantry.store_flour.<locals>.seal",
                        "STORE_ATTR",
                    ),
                    orders,
                    main,
                ],
                running,
            ),
        ],
        2: [
            (
                56,
                [
                    frame("threading.py:366", "Condition.wait", "CALL"),
                    frame("bakery/proofer.py:802", "Proofer.watch"),
                    worker,
                ],
                0,
            ),
            (
                6,
                [frame("bakery/ledger.py:1427", "Ledger.flush", "LOAD_FAST"), worker],
                THREAD_STATUS_GIL_REQUESTED,
            ),
        ],
    }


def child() -> None:
    """Draw Tachyon's live mode on this terminal, from synthetic samples."""
    # Imported here, like in bakery(): curses is missing from Windows too.
    import curses

    from profiling.sampling.live_collector import LiveStatsCollector

    rng = random.Random(1907)
    threads = {
        thread_id: (
            [stack for _, stack, _ in options],
            [status for _, _, status in options],
            [weight for weight, _, _ in options],
        )
        for thread_id, options in bakery().items()
    }

    def sample() -> list[InterpreterInfo]:
        infos = []
        for thread_id, (stacks, statuses, weights) in threads.items():
            # The proofing thread is only caught one sample in eight.
            if thread_id != 1 and rng.random() > 0.125:
                continue
            index = rng.choices(range(len(stacks)), weights)[0]
            infos.append(ThreadInfo(thread_id, stacks[index], statuses[index]))
        return [InterpreterInfo(0, infos)]

    collector = LiveStatsCollector(
        100, sort_by="tottime", limit=40, pid=4242, opcodes=True
    )

    def drive(stdscr) -> None:
        collector.init_curses(stdscr)
        try:
            start = time.perf_counter()
            fed = 0
            while (elapsed := time.perf_counter() - start) < LIVE_SECONDS:
                for _ in range(min(int(elapsed * RATE) - fed, 400)):
                    collector.collect(sample())
                    fed += 1
                time.sleep(0.001)
            collector.mark_finished()
            stop = time.perf_counter() + FINISHED_SECONDS
            while time.perf_counter() < stop:
                collector._handle_input()
                time.sleep(0.05)
        finally:
            collector.cleanup_curses()

    curses.wrapper(drive)


def record() -> None:
    """Run {func}`child` under a pseudo-terminal and write what it drew."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COLORTERM", "LC_", "NO_COLOR", "TERM"))
    }
    environment.update(
        COLUMNS=str(COLUMNS),
        FORCE_COLOR="1",
        LANG="en_US.UTF-8",
        LINES=str(ROWS),
        TERM="xterm-256color",
    )
    parent, terminal = pty.openpty()
    fcntl.ioctl(terminal, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLUMNS, 0, 0))
    started = time.monotonic()
    process = subprocess.Popen(
        (sys.executable, __file__, "--child"),
        stdin=terminal,
        stdout=terminal,
        stderr=terminal,
        env=environment,
        close_fds=True,
    )
    os.close(terminal)
    decoder = codecs.getincrementaldecoder("UTF-8")(errors="replace")
    events = []
    while True:
        readable, _, _ = select.select([parent], [], [], 0.05)
        if not readable:
            if process.poll() is not None:
                break
            continue
        try:
            data = os.read(parent, 65536)
        except OSError:
            break
        if not data:
            break
        text = decoder.decode(data)
        if text:
            events.append((round(time.monotonic() - started, 6), text))
    process.wait()
    os.close(parent)
    header = {
        "version": 2,
        "width": COLUMNS,
        "height": ROWS,
        "env": {"TERM": "xterm-256color"},
        "title": "python -m profiling.sampling run --live --opcodes",
    }
    lines = [json.dumps(header, ensure_ascii=False)]
    lines.extend(json.dumps([at, "o", text], ensure_ascii=False) for at, text in events)
    CAST.write_text("\n".join(lines) + "\n", encoding="UTF-8")
    print(f"Wrote {len(events)} events to {CAST}.")


if __name__ == "__main__":
    if "--child" in sys.argv:
        child()
    else:
        record()
