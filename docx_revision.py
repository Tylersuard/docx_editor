import zipfile
from datetime import datetime
from pathlib import Path
from lxml import etree

NAMESPACE = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
}


def qn(tag):
    return f"{{{NAMESPACE['w']}}}{tag}"


class DocxRevisionEditor:
    """A simple editor to make tracked changes in a docx file."""

    def __init__(self, path):
        self.path = Path(path)
        self.zip = zipfile.ZipFile(self.path, 'r')
        self.tree = etree.fromstring(self.zip.read('word/document.xml'))
        self.comments_tree = None
        self.content_types = etree.fromstring(self.zip.read('[Content_Types].xml'))
        self.rels_tree = etree.fromstring(self.zip.read('word/_rels/document.xml.rels'))
        if 'word/comments.xml' in self.zip.namelist():
            self.comments_tree = etree.fromstring(self.zip.read('word/comments.xml'))

    def _ensure_comments_part(self):
        """Ensure comments part exists in content types and relationships."""
        ns_ct = {'ct': 'http://schemas.openxmlformats.org/package/2006/content-types'}
        has_override = any(el.get('PartName') == '/word/comments.xml' for el in self.content_types.findall('ct:Override', ns_ct))
        if not has_override:
            override = etree.Element('Override', PartName='/word/comments.xml',
                                     ContentType='application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml')
            self.content_types.append(override)

        ns_rel = {'rel': 'http://schemas.openxmlformats.org/package/2006/relationships'}
        has_rel = any(rel.get('Type').endswith('/comments') for rel in self.rels_tree.findall('rel:Relationship', ns_rel))
        if not has_rel:
            rid_numbers = [int(rel.get('Id')[3:]) for rel in self.rels_tree.findall('rel:Relationship', ns_rel) if rel.get('Id').startswith('rId')]
            next_rid = max(rid_numbers or [0]) + 1
            rel = etree.Element('{http://schemas.openxmlformats.org/package/2006/relationships}Relationship',
                                Id=f'rId{next_rid}',
                                Type='http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments',
                                Target='comments.xml')
            self.rels_tree.append(rel)

    def _write_back(self, output_path):
        with zipfile.ZipFile(output_path, 'w') as new_zip:
            names = set(self.zip.namelist())
            for item in self.zip.infolist():
                if item.filename == 'word/document.xml':
                    data = etree.tostring(self.tree, xml_declaration=True, encoding='UTF-8', standalone='yes')
                    new_zip.writestr(item, data)
                elif item.filename == 'word/comments.xml':
                    if self.comments_tree is not None:
                        data = etree.tostring(self.comments_tree, xml_declaration=True, encoding='UTF-8', standalone='yes')
                        new_zip.writestr(item, data)
                elif item.filename == '[Content_Types].xml':
                    data = etree.tostring(self.content_types, xml_declaration=True, encoding='UTF-8', standalone='yes')
                    new_zip.writestr(item, data)
                elif item.filename == 'word/_rels/document.xml.rels':
                    data = etree.tostring(self.rels_tree, xml_declaration=True, encoding='UTF-8', standalone='yes')
                    new_zip.writestr(item, data)
                else:
                    new_zip.writestr(item, self.zip.read(item.filename))

            if self.comments_tree is not None and 'word/comments.xml' not in names:
                data = etree.tostring(self.comments_tree, xml_declaration=True, encoding='UTF-8', standalone='yes')
                new_zip.writestr('word/comments.xml', data)

    def save(self, output_path):
        self._write_back(output_path)

    def _create_run(self, text):
        r = etree.Element(qn('r'))
        t = etree.SubElement(r, qn('t'))
        t.text = text
        return r

    def add_text(self, paragraph_index, text, author, date=None):
        """Insert text as a tracked insertion at a paragraph index."""
        date = date or datetime.utcnow().isoformat()
        paragraphs = self.tree.findall('.//w:p', NAMESPACE)
        if paragraph_index >= len(paragraphs):
            raise IndexError('Paragraph index out of range')
        ins = etree.Element(qn('ins'), attrib={qn('author'): author, qn('date'): date})
        ins.append(self._create_run(text))
        paragraphs[paragraph_index].append(ins)

    def delete_text(self, text, author, date=None):
        """Delete first occurrence of text with tracking."""
        date = date or datetime.utcnow().isoformat()
        for t_el in self.tree.findall('.//w:t', NAMESPACE):
            if t_el.text and text in t_el.text:
                parent_r = t_el.getparent()
                del_el = etree.Element(qn('del'), attrib={qn('author'): author, qn('date'): date})
                del_run = etree.Element(qn('r'))
                del_text = etree.Element(qn('delText'))
                del_text.text = text
                del_run.append(del_text)
                del_el.append(del_run)
                new_text = t_el.text.replace(text, '')
                if new_text:
                    t_el.text = new_text
                    parent_r.addnext(del_el)
                else:
                    parent_r.addnext(del_el)
                    parent_r.getparent().remove(parent_r)
                return True
        return False

    def highlight_text(self, text, color='yellow', author='author', date=None):
        """Highlight text with tracked change."""
        date = date or datetime.utcnow().isoformat()
        for t_el in self.tree.findall('.//w:t', NAMESPACE):
            if t_el.text and text in t_el.text:
                ins = etree.Element(qn('ins'), attrib={qn('author'): author, qn('date'): date})
                r = etree.Element(qn('r'))
                rPr = etree.SubElement(r, qn('rPr'))
                highlight = etree.SubElement(rPr, qn('highlight'), attrib={qn('val'): color})
                t = etree.SubElement(r, qn('t'))
                t.text = text
                ins.append(r)
                parent_r = t_el.getparent()
                new_text = t_el.text.replace(text, '')
                if new_text:
                    t_el.text = new_text
                    parent_r.addnext(ins)
                else:
                    parent_r.addnext(ins)
                    parent_r.getparent().remove(parent_r)
                return True
        return False

    def add_comment(self, text, comment_text, author, date=None):
        """Add a comment to the first occurrence of text."""
        date = date or datetime.utcnow().isoformat()
        if self.comments_tree is None:
            root = etree.Element(qn('comments'), nsmap={'w': NAMESPACE['w']})
            self.comments_tree = root
            self._ensure_comments_part()
        max_id = 0
        for c in self.comments_tree.findall('.//w:comment', NAMESPACE):
            cid = int(c.get(qn('id')))
            if cid > max_id:
                max_id = cid
        comment_id = str(max_id + 1)
        comment_el = etree.SubElement(self.comments_tree, qn('comment'), attrib={qn('id'): comment_id, qn('author'): author, qn('date'): date})
        p = etree.SubElement(comment_el, qn('p'))
        r = etree.SubElement(p, qn('r'))
        t = etree.SubElement(r, qn('t'))
        t.text = comment_text

        for t_el in self.tree.findall('.//w:t', NAMESPACE):
            if t_el.text and text in t_el.text:
                start = etree.Element(qn('commentRangeStart'), attrib={qn('id'): comment_id})
                end = etree.Element(qn('commentRangeEnd'), attrib={qn('id'): comment_id})
                ref = etree.Element(qn('r'))
                ref_prop = etree.SubElement(ref, qn('rPr'))
                com_ref = etree.SubElement(ref_prop, qn('commentReference'), attrib={qn('id'): comment_id})
                parent_r = t_el.getparent()
                parent_p = parent_r.getparent()
                parent_p.insert(parent_p.index(parent_r), start)
                parent_p.insert(parent_p.index(parent_r) + 1, end)
                parent_p.insert(parent_p.index(end) + 1, ref)
                return True
        return False
