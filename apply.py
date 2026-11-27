#!/usr/bin/env python3
"""Run the tagged code blocks of the numbered setup docs (README.md explains the tags).

  ./apply.py                      list every doc and whether it applies to this server
  ./apply.py 100-network.md ...   apply the named docs, then run their verify blocks
  ./apply.py --verify [doc ...]   only the verify blocks; no docs = all docs
  ./apply.py --extract doc ...    print the shell blocks (| shellcheck -s bash -)

It knows nothing about order or content: what to apply, and when, is up to you.

  LANPARTY_ENV    the server description (default /etc/lanparty/env)
  LANPARTY_HOOKS  directory with NNN.sh scripts that stand in for doc NNN's manual
                  blocks (a VM supplies them; a person does the manual steps instead)

Exit status: the number of failed blocks (applying stops at the first failure).
"""
import argparse
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
SHELL_LANGS = {"", "sh", "bash", "shell"}
KINDS = {"run", "verify", "manual"}


@dataclass
class Block:
    line: int             # line of the opening fence, for messages
    lang: str             # sh, ini, ... ("" if none)
    kind: str             # file, run, verify or manual
    heading: str          # the heading the block sits under
    body: str = ""
    path: str = ""        # file=
    mode: str = "0644"    # mode=
    cond: str = ""        # if=

    @property
    def label(self):
        """A block's first comment line says what it does; else its heading."""
        first = self.body.lstrip().split("\n", 1)[0]
        return first[1:].strip() if first.startswith("#") and not first.startswith("#!") else self.heading


@dataclass
class Doc:
    path: Path
    requires: str = ""
    blocks: list = field(default_factory=list)
    hooked: bool = False  # the manual-block hook already ran
    manual_pending: bool = False  # a manual block was printed for a person to do

    @property
    def name(self):
        return self.path.name

    @property
    def number(self):
        return self.name.split("-", 1)[0]


def parse_doc(path):
    """Collect the tagged blocks of a markdown doc; untagged blocks are prose."""
    doc = Doc(path)
    heading, fence, block = "", None, None
    for no, line in enumerate(path.read_text().splitlines(), 1):
        if fence:
            stripped = line.rstrip()
            if stripped and set(stripped) == {fence[0]} and len(stripped) >= len(fence):
                if block:
                    doc.blocks.append(block)
                fence, block = None, None
            elif block:
                block.body += line + "\n"
            continue
        m = re.match(r"<!--\s*requires:\s*(.*?)\s*-->", line)
        if m:
            doc.requires = re.sub(r"feature\s+", "feature:", m.group(1))
            continue
        m = re.match(r"#+\s+(.*)", line)
        if m:
            heading = m.group(1).strip()
            continue
        m = re.match(r"(`{3,}|~{3,})(.*)", line)
        if not m:
            continue
        fence, words = m.group(1), m.group(2).split()
        lang = words.pop(0) if words and "=" not in words[0] and words[0] not in KINDS else ""
        block = Block(no, lang, "", heading)
        for w in words:
            key, _, value = w.partition("=")
            if w in KINDS:
                block.kind = w
            elif key == "file":
                block.kind, block.path = "file", value
            elif key == "mode":
                block.mode = value
            elif key == "if":
                block.cond = value
        if not block.kind:
            block = None
    return doc


def read_env(path):
    """KEY=value lines (shell quoting allowed, no shell logic); # starts a comment."""
    env = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parts = shlex.split(value, comments=True)
        env[key.strip()] = " ".join(parts)
    return env


def holds(cond, env):
    """All comma-separated conditions hold: VAR, !VAR, feature:NAME, !feature:NAME."""
    for c in filter(None, (c.strip() for c in cond.split(","))):
        negate = c.startswith("!")
        c = c.lstrip("!")
        if c.startswith("feature:"):
            value = c[len("feature:"):] in env.get("FEATURES", "").split()
        else:
            value = env.get(c, "") not in ("", "no")
        if value == negate:
            return False
    return True


def substitute(text, env):
    """Replace ${NAME} for names defined in the env file; everything else stays."""
    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}",
                  lambda m: env.get(m.group(1), m.group(0)), text)


def run_shell(body, env):
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as f:
        f.write(body)
    try:
        # apt asks nothing and debconf does not look for a terminal it will not get
        base = {"DEBIAN_FRONTEND": "noninteractive", **os.environ}
        return subprocess.run(["bash", "-e", f.name], cwd=HERE,
                              env={**base, **env}).returncode == 0
    finally:
        os.unlink(f.name)


def write_file(block, env):
    target = Path(block.path)
    content = substitute(block.body, env)
    if target.is_symlink():
        target.unlink()  # the block is the whole file: replace a link, never write through it
    elif target.is_file() and target.read_text() == content:
        os.chmod(target, int(block.mode, 8))
        return "unchanged"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    os.chmod(target, int(block.mode, 8))
    return "written"


class Runner:
    def __init__(self, env, hooks):
        self.env, self.hooks, self.failed = env, hooks, 0

    def fail(self, where, why):
        print(f"  FAILED  {where} {why}")
        self.failed += 1

    def block(self, doc, b):
        """Run one block; False means stop applying."""
        where = f"{doc.name}:{b.line}"
        if b.cond and not holds(b.cond, self.env):
            print(f"  skip    {where} ({b.label}; if={b.cond})")
            return True
        if b.kind == "file":
            try:
                print(f"  file    {b.path} ({write_file(b, self.env)})")
                return True
            except OSError as e:
                self.fail(where, f"could not write {b.path}: {e}")
                return False
        if b.kind in ("run", "verify"):
            if b.lang not in SHELL_LANGS:
                self.fail(where, f"cannot run '{b.lang}' blocks")
                return False
            if run_shell(b.body, self.env):
                if b.kind == "verify":
                    print(f"  ok      {where} ({b.label})")
                return True
            self.fail(where, f"({b.label})")
            return False
        # manual: a hook stands in for all of the doc's manual blocks, once
        hook = Path(self.hooks, f"{doc.number}.sh") if self.hooks else None
        if hook and hook.is_file():
            if doc.hooked:
                return True
            doc.hooked = True
            if run_shell(hook.read_text(), self.env):
                print(f"  hook    {hook}")
                return True
            self.fail(where, f"hook {hook}")
            return False
        print(f"  MANUAL  {where} ({b.label}) -- do this yourself:")
        for line in b.body.splitlines():
            print(f"          | {line}")
        doc.manual_pending = True
        return True

    def apply(self, doc):
        """"ok", "failed", or "manual" (checks fail while printed manual steps are still open)."""
        print(f"=== {doc.name}")
        for b in doc.blocks:
            if b.kind != "verify" and not self.block(doc, b):
                return "failed"
        if self.verify(doc, header=False):
            return "ok"  # also when manual steps were printed: evidently done already
        if doc.manual_pending:
            print(f"  checks  fail -- do the MANUAL steps above, then: ./apply.py --verify {doc.name}")
            return "manual"
        return "failed"

    def verify(self, doc, header=True):
        if header:
            print(f"=== {doc.name}")
        before = self.failed
        for b in doc.blocks:
            if b.kind == "verify":
                self.block(doc, b)
        return self.failed == before


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=__doc__.split("\n\n", 1)[1])
    g = p.add_mutually_exclusive_group()
    g.add_argument("--verify", action="store_true", help="only run verify blocks")
    g.add_argument("--extract", action="store_true", help="print the shell blocks")
    p.add_argument("docs", nargs="*", type=Path)
    args = p.parse_args()
    # our lines and the blocks' own output must interleave in the right order
    sys.stdout.reconfigure(line_buffering=True)

    if args.extract and not args.docs:
        p.error("--extract needs docs")
    docs = args.docs or sorted(HERE.glob("[0-9][0-9][0-9]-*.md"))
    if not docs:
        p.error(f"no numbered docs in {HERE}")

    if args.extract:
        for path in docs:
            doc = parse_doc(path)
            for b in doc.blocks:
                shell = b.lang in SHELL_LANGS if b.kind != "file" else b.lang in ("sh", "bash")
                if shell and b.kind != "manual":
                    what = f"{b.kind} {b.path}" if b.path else b.kind
                    print(f"\n# --- {doc.name}:{b.line} {what} ({b.label})")
                    print(b.body, end="")
        return 0

    env_path = os.environ.get("LANPARTY_ENV", "/etc/lanparty/env")
    try:
        env = read_env(env_path)
    except OSError:
        print(f"no env file at {env_path} (set LANPARTY_ENV, see 000-server.md)", file=sys.stderr)
        if args.docs or args.verify:
            return 2
        env = {}

    runner = Runner(env, os.environ.get("LANPARTY_HOOKS", ""))
    for path in docs:
        doc = parse_doc(path)
        if not holds(doc.requires, env):
            print(f"skip  {doc.name} (requires: {doc.requires})")
            continue
        if args.verify:
            runner.verify(doc)
        elif args.docs:
            result = runner.apply(doc)
            if result != "ok":
                print(f"stopped at {doc.name}" + (": do its manual steps first" if result == "manual" else ""))
                break
        else:
            kinds = {}
            for b in doc.blocks:
                kinds[b.kind] = kinds.get(b.kind, 0) + 1
            summary = ", ".join(f"{n} {k}" for k, n in kinds.items()) or "nothing to run"
            print(f"apply {doc.name} ({summary})")
    return min(runner.failed, 255)


if __name__ == "__main__":
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # quiet exit when piped into head
    sys.exit(main())
