"""Build a portable source ZIP without device images, credentials or state."""
import argparse
from pathlib import Path
import zipfile


SOURCE = Path(__file__).resolve().parent
RUNTIME_FILES = (
    'Launch.cmd', 'Launch.command', 'README.md', 'requirements.txt',
    'simulator.py', 'lvgl_sim.py', 'fat_image.py', 'font_sim.py',
    'fs_driver_sim.py', 'timer_sim.py',
    'test-data/stop_740032188_formatted.json',
    'fonts/symbols.json', 'fonts/README.md',
    'fonts/LICENSE-Montserrat.txt', 'fonts/LICENSE-Font-Awesome.txt',
) + tuple(f'fonts/sim_montserrat_{size}.bin' for size in range(12, 50, 2))


def build_archive(destination):
    """Package only the simulator's required source, data and font licenses."""
    destination = Path(destination).resolve()
    files = [(SOURCE / name, name) for name in RUNTIME_FILES]
    files.append((SOURCE.parent / 'LICENSE', 'LICENSE'))
    for source, _name in files:
        if not source.is_file():
            raise FileNotFoundError(f'Missing distribution file: {source}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w') as archive:
        for source, name in files:
            entry = zipfile.ZipInfo('t4s3-simulator/' + name)
            entry.create_system = 3
            entry.external_attr = (0o100755 if name == 'Launch.command' else 0o100644) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, source.read_bytes())
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', nargs='?', type=Path,
                        default=SOURCE / 'dist' / 't4s3-simulator.zip')
    print(build_archive(parser.parse_args().output))
