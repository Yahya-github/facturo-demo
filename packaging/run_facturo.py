"""PyInstaller entry script (Analysis cannot start from a package __main__)."""

from facturo.__main__ import main

if __name__ == "__main__":
    main()
