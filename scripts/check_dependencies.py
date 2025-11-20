#!/usr/bin/env python3
"""Check that all imports in the codebase have corresponding dependencies."""

import ast
import sys
from pathlib import Path
from typing import Set, Dict

# Mapping of import names to package names (when they differ)
IMPORT_TO_PACKAGE = {
    'PIL': 'Pillow',
    'bs4': 'beautifulsoup4',
    'yaml': 'pyyaml',
    'dotenv': 'python-dotenv',
    'flask': 'flask',
    'werkzeug': 'flask',  # Part of flask
    'usb': 'pyusb',
    'usb1': 'libusb1',  # Optional USB library
    'telegram': 'python-telegram-bot',
}

# Standard library modules (Python 3.11+)
STDLIB_MODULES = {
    'abc', 'aifc', 'argparse', 'array', 'ast', 'asynchat', 'asyncio', 'asyncore',
    'atexit', 'audioop', 'base64', 'bdb', 'binascii', 'binhex', 'bisect', 'builtins',
    'bz2', 'calendar', 'cgi', 'cgitb', 'chunk', 'cmath', 'cmd', 'code', 'codecs',
    'codeop', 'collections', 'colorsys', 'compileall', 'concurrent', 'configparser',
    'contextlib', 'contextvars', 'copy', 'copyreg', 'cProfile', 'crypt', 'csv',
    'ctypes', 'curses', 'dataclasses', 'datetime', 'dbm', 'decimal', 'difflib',
    'dis', 'distutils', 'doctest', 'email', 'encodings', 'enum', 'errno', 'faulthandler',
    'fcntl', 'filecmp', 'fileinput', 'fnmatch', 'fractions', 'ftplib', 'functools',
    'gc', 'getopt', 'getpass', 'gettext', 'glob', 'graphlib', 'grp', 'gzip', 'hashlib',
    'heapq', 'hmac', 'html', 'http', 'idlelib', 'imaplib', 'imghdr', 'imp', 'importlib',
    'inspect', 'io', 'ipaddress', 'itertools', 'json', 'keyword', 'lib2to3', 'linecache',
    'locale', 'logging', 'lzma', 'mailbox', 'mailcap', 'marshal', 'math', 'mimetypes',
    'mmap', 'modulefinder', 'msilib', 'msvcrt', 'multiprocessing', 'netrc', 'nis',
    'nntplib', 'numbers', 'operator', 'optparse', 'os', 'ossaudiodev', 'pathlib',
    'pdb', 'pickle', 'pickletools', 'pipes', 'pkgutil', 'platform', 'plistlib', 'poplib',
    'posix', 'posixpath', 'pprint', 'profile', 'pstats', 'pty', 'pwd', 'py_compile',
    'pyclbr', 'pydoc', 'queue', 'quopri', 'random', 're', 'readline', 'reprlib',
    'resource', 'rlcompleter', 'runpy', 'sched', 'secrets', 'select', 'selectors',
    'shelve', 'shlex', 'shutil', 'signal', 'site', 'smtpd', 'smtplib', 'sndhdr',
    'socket', 'socketserver', 'spwd', 'sqlite3', 'ssl', 'stat', 'statistics', 'string',
    'stringprep', 'struct', 'subprocess', 'sunau', 'symbol', 'symtable', 'sys',
    'sysconfig', 'syslog', 'tabnanny', 'tarfile', 'telnetlib', 'tempfile', 'termios',
    'test', 'textwrap', 'threading', 'time', 'timeit', 'tkinter', 'token', 'tokenize',
    'tomllib', 'trace', 'traceback', 'tracemalloc', 'tty', 'turtle', 'turtledemo',
    'types', 'typing', 'unicodedata', 'unittest', 'urllib', 'uu', 'uuid', 'venv',
    'warnings', 'wave', 'weakref', 'webbrowser', 'winreg', 'winsound', 'wsgiref',
    'xdrlib', 'xml', 'xmlrpc', 'zipapp', 'zipfile', 'zipimport', 'zlib', '_thread',
}

def extract_imports_from_file(file_path: Path) -> Set[str]:
    """Extract all top-level imports from a Python file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            tree = ast.parse(f.read(), filename=str(file_path))
    except SyntaxError:
        print(f"Warning: Syntax error in {file_path}")
        return set()

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # Get top-level module name
                module = alias.name.split('.')[0]
                imports.add(module)
        elif isinstance(node, ast.ImportFrom):
            # Skip relative imports (from . import X or from .. import X)
            if node.level > 0:
                continue
            if node.module:
                # Get top-level module name
                module = node.module.split('.')[0]
                imports.add(module)

    return imports

def get_all_imports(src_dir: Path) -> Dict[str, Set[Path]]:
    """Get all imports from all Python files, grouped by module."""
    all_imports = {}

    for py_file in src_dir.rglob('*.py'):
        # Skip test files
        if 'test' in str(py_file):
            continue

        imports = extract_imports_from_file(py_file)

        for imp in imports:
            if imp not in all_imports:
                all_imports[imp] = set()
            all_imports[imp].add(py_file)

    return all_imports

def read_dependencies_from_pyproject(pyproject_path: Path) -> Dict[str, Set[str]]:
    """Read all dependencies from pyproject.toml."""
    import re

    with open(pyproject_path, 'r') as f:
        content = f.read()

    deps = {
        'core': set(),
        'optional': set(),
    }

    # Extract core dependencies
    core_match = re.search(r'dependencies = \[(.*?)\]', content, re.DOTALL)
    if core_match:
        for line in core_match.group(1).split('\n'):
            if '">=' in line or '==' in line:
                pkg = line.split('"')[1].split('>=')[0].split('==')[0].lower()
                deps['core'].add(pkg)

    # Extract optional dependencies
    optional_section = re.search(r'\[project\.optional-dependencies\](.*?)(?:\[|$)', content, re.DOTALL)
    if optional_section:
        for line in optional_section.group(1).split('\n'):
            if '">=' in line or '==' in line:
                pkg = line.split('"')[1].split('>=')[0].split('==')[0].lower()
                deps['optional'].add(pkg)

    return deps

def main():
    project_root = Path(__file__).parent.parent
    src_dir = project_root / 'src' / 'holocene'
    pyproject_path = project_root / 'pyproject.toml'

    print("🔍 Scanning imports in codebase...\n")

    all_imports = get_all_imports(src_dir)
    deps = read_dependencies_from_pyproject(pyproject_path)

    all_deps = deps['core'] | deps['optional']

    # Filter out internal modules and stdlib
    external_imports = {}
    # Internal holocene modules (top-level packages within holocene)
    internal_modules = {
        'holocene', 'api', 'config', 'core', 'daemon', 'storage', 'llm',
        'integrations', 'research', 'plugins', 'cli',
        # Submodules often imported directly
        'models', 'loader', 'channels', 'plugin', 'plugin_registry', 'holocene_core',
        'database', 'nanogpt', 'router', 'budget', 'holod',
        # Integration submodules
        'journel', 'git_scanner', 'internet_archive', 'bookmarks', 'calibre', 'mercadolivre',
        'client', 'renderer', 'spinitex',
        # CLI submodules
        'config_commands', 'stats_commands', 'daemon_commands', 'inventory_commands',
        'ml_inventory_commands', 'mercadolivre_commands', 'print_commands',
        # Research submodules
        'orchestrator', 'pdf_handler', 'pdf_metadata_extractor', 'book_enrichment',
        'book_importer', 'bibtex_importer', 'crossref_client', 'openalex_client',
        'internet_archive_client', 'unpaywall_client', 'wikipedia_client',
        'report_generator', 'dewey_classifier', 'udc_classifier', 'extended_dewey',
    }

    for module, files in all_imports.items():
        # Skip internal modules
        if module in internal_modules:
            continue

        # Skip standard library
        if module in STDLIB_MODULES:
            continue

        # Map import name to package name
        package = IMPORT_TO_PACKAGE.get(module, module).lower()
        external_imports[package] = (module, files)

    # Find missing dependencies
    missing = []
    for package, (import_name, files) in sorted(external_imports.items()):
        if package not in all_deps:
            missing.append((package, import_name, files))

    if missing:
        print("❌ Missing dependencies found:\n")
        for package, import_name, files in missing:
            print(f"  📦 {package} (imported as '{import_name}')")
            for f in sorted(files)[:3]:  # Show first 3 files
                rel_path = f.relative_to(project_root)
                print(f"     - {rel_path}")
            if len(files) > 3:
                print(f"     ... and {len(files) - 3} more files")
            print()

        print(f"\n💡 Add these to pyproject.toml in the appropriate dependency group.\n")
        return 1
    else:
        print("✅ All external imports have corresponding dependencies!\n")

        # Show what's being used
        print("📊 External packages in use:")
        for package in sorted(external_imports.keys()):
            group = 'core' if package in deps['core'] else 'optional'
            print(f"  ✓ {package} ({group})")

        return 0

if __name__ == '__main__':
    sys.exit(main())
