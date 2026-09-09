"""CBZ file reader - extracts metadata from ComicInfo.xml."""

import zipfile
from pathlib import Path

from comicdesk.models import Comic
from comicdesk.services.comicinfo import parse_comicinfo


def read_cbz_metadata(cbz_path: Path) -> Comic:
    """
    Read metadata from a CBZ file.
    
    Args:
        cbz_path: Path to the CBZ file
        
    Returns:
        Comic object with extracted metadata
    """
    comic = Comic(path=cbz_path)
    
    try:
        with zipfile.ZipFile(cbz_path, "r") as zf:
            # Find ComicInfo.xml (case-insensitive)
            xml_name = None
            for name in zf.namelist():
                if name.lower() == "comicinfo.xml":
                    xml_name = name
                    break
            
            if not xml_name:
                return comic
            
            comic = parse_comicinfo(zf.read(xml_name), cbz_path)
    
    except (zipfile.BadZipFile, OSError, ValueError):
        pass
    
    return comic


def scan_folder(folder_path: Path, recursive: bool = True) -> list[Comic]:
    """
    Scan a folder for CBZ files and read their metadata.
    
    Args:
        folder_path: Path to scan
        recursive: If True, scan subfolders
        
    Returns:
        List of Comic objects
    """
    comics = []
    pattern = "**/*.cbz" if recursive else "*.cbz"
    
    for cbz_file in sorted(folder_path.glob(pattern)):
        if cbz_file.is_file():
            comic = read_cbz_metadata(cbz_file)
            comics.append(comic)
    
    return comics
