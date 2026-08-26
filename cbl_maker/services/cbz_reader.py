"""CBZ file reader - extracts metadata from ComicInfo.xml."""

import zipfile
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET

from cbl_maker.models import Comic
from cbl_maker.utils.url_parser import extract_all_cv_ids


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
            
            # Read and parse XML
            xml_content = zf.read(xml_name)
            
            # Try UTF-8 first, fallback to Latin-1
            try:
                xml_text = xml_content.decode("utf-8")
            except UnicodeDecodeError:
                xml_text = xml_content.decode("latin-1")
            
            root = ET.fromstring(xml_text)
            
            # Extract fields
            comic.series_name = _get_text(root, "Series", "")
            comic.volume = _get_text(root, "Volume", "")
            comic.issue_number = _get_text(root, "Number", "")
            comic.year = _get_text(root, "Year", "")
            comic.title = _get_text(root, "Title", "")
            comic.month = _get_text(root, "Month", "")
            comic.day = _get_text(root, "Day", "")
            
            # Extract Comic Vine URLs from Web and Notes fields
            web_field = _get_text(root, "Web", "")
            notes_field = _get_text(root, "Notes", "")
            
            combined_text = f"{web_field} {notes_field}"
            cv_ids_list = extract_all_cv_ids(combined_text)
            
            # Store URLs and IDs
            if web_field:
                comic.web_links.append(web_field)
            
            # Get first CV IDs found
            if cv_ids_list:
                first_ids = cv_ids_list[0]
                comic.cv_series_id = first_ids.get("series_id")
                comic.cv_issue_id = first_ids.get("issue_id")
    
    except (zipfile.BadZipFile, ET.ParseError):
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


def _get_text(element: ET.Element, tag: str, default: str = "") -> str:
    """Get text content of an XML element."""
    child = element.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return default
