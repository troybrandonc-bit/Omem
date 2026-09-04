"""Put the reference validator in the wheel at build time.

The point of this package is that a LangGraph user can go from nothing to a
checked record without cloning anything. Emitting a record they cannot then
validate would leave them holding a file and a claim, which is the situation
the specification exists to end.

So `pip install testimony-langgraph` ships `testimony-validate` as well. The
validator is one standard-library file with no network access, and it is the
same file the repository uses, copied at build time rather than committed
twice. A second copy is a second copy to drift, and a validator that disagrees
with itself is worse than no validator.

When the source tree is absent and the copy is already here, that is the sdist
case: a wheel built from an sdist has no ../../scripts to read, and the file it
carries is the right one.
"""
import os
import shutil

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

SOURCE = os.path.join("..", "..", "scripts", "testimony_validate.py")
DEST = "testimony_validate.py"


class BundleValidator(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version, build_data):
        here = os.path.dirname(os.path.abspath(__file__))
        src = os.path.normpath(os.path.join(here, SOURCE))
        dst = os.path.join(here, DEST)

        if not os.path.exists(src):
            if os.path.exists(dst):
                return          # building from an sdist; the copy is correct
            raise RuntimeError(
                "cannot find %s and no bundled copy is present. The wheel would "
                "install a testimony-validate command that does not exist." % src)

        shutil.copyfile(src, dst)
        # Belt and braces: a wheel whose validator does not import is worse than
        # one without it, because the failure appears in the user's terminal
        # rather than in this build.
        with open(dst, encoding="utf-8") as fh:
            text = fh.read()
        if "def main(" not in text or "def validate(" not in text:
            raise RuntimeError(
                "the bundled validator has no main() or validate(); the console "
                "script would be dead on arrival")
