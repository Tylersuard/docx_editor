# Docx Editor

This repository provides a simple Python helper to make tracked changes in a `.docx` file using low level XML manipulation.  The main entry point is the `DocxRevisionEditor` class found in `docx_revision.py`.

## Basic Usage

```python
from docx_revision import DocxRevisionEditor

# Load a document
editor = DocxRevisionEditor('input.docx')

# Make tracked changes
editor.add_text(0, 'Inserted text', author='Alice')
editor.delete_text('target', author='Alice')
editor.highlight_text('highlight me', color='yellow', author='Alice')
editor.add_comment('highlight me', 'My comment', author='Alice')

# Save result
editor.save('output.docx')
```

All changes are written as WordprocessingML elements (`w:ins`, `w:del`, comments, etc.) so that Microsoft Word will show them as standard revisions.
