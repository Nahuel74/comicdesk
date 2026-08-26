"""CBL file writer - generates ComicRack compatible reading lists."""

from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString

from cbl_maker.models import ReadingList, Comic


def generate_cbl(reading_list: ReadingList) -> str:
    """
    Generate CBL XML from a reading list.
    
    Args:
        reading_list: ReadingList to convert
        
    Returns:
        XML string in ComicRack CBL format
    """
    # Root element with namespaces
    root = Element("ReadingList")
    root.set("xmlns:xsd", "http://www.w3.org/2001/XMLSchema")
    root.set("xmlns:xsi", "http://www.w3.org/2001/XMLSchema-instance")
    
    # Name
    name_elem = SubElement(root, "Name")
    name_elem.text = reading_list.name
    
    # Books
    books_elem = SubElement(root, "Books")
    
    for comic in reading_list.comics:
        book_elem = SubElement(books_elem, "Book")
        book_elem.set("SeriesName", comic.series_name)
        book_elem.set("Volume", comic.volume)
        book_elem.set("Issue", comic.issue_number)
        
        # Add Database element if CV IDs are present
        if comic.has_cv_ids:
            db_elem = SubElement(book_elem, "Database")
            db_elem.set("Name", "cv")
            db_elem.set("Series", comic.cv_series_id or "")
            db_elem.set("Issue", comic.cv_issue_id or "")
    
    # Matchers (empty)
    SubElement(root, "Matchers")
    
    # Convert to string with pretty printing
    rough_string = tostring(root, encoding="unicode", xml_declaration=False)
    xml_declaration = '<?xml version="1.0" encoding="utf-8"?>\n'
    
    # Pretty print
    dom = parseString(xml_declaration + rough_string)
    pretty_xml = dom.toprettyxml(indent="\t", encoding=None)
    
    # Remove extra XML declaration added by toprettyxml
    lines = pretty_xml.split("\n")
    if lines[0].startswith("<?xml"):
        lines = lines[1:]
    
    return xml_declaration + "\n".join(lines)


def save_cbl(xml_content: str, output_path: Path) -> None:
    """
    Save CBL XML to file.
    
    Args:
        xml_content: XML string to save
        output_path: Path to save the file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(xml_content)
