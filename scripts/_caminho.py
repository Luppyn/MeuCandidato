"""Coloca a raiz do projeto no sys.path para os scripts acharem banco.py."""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
