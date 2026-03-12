"""
Document Processing Service
Handles extraction of text from PDF and Word documents
"""

import os
import re
from typing import Optional, Dict, List, Tuple
from pathlib import Path
import logging

# PDF processing
import PyPDF2
from PyPDF2 import PdfReader

# Word processing
import docx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DocumentProcessor:
    """Main document processing class"""
    
    def __init__(self):
        self.supported_formats = ['.pdf', '.docx']
        
    def process(self, file_path: str) -> Dict:
        """
        Main entry point - process any supported document
        
        Args:
            file_path: Path to the document
            
        Returns:
            Dictionary with extracted text and metadata
        """
        file_ext = Path(file_path).suffix.lower()
        
        if file_ext not in self.supported_formats:
            raise ValueError(f"Unsupported format: {file_ext}. Supported: {self.supported_formats}")
        
        # Extract based on file type
        if file_ext == '.pdf':
            return self._process_pdf(file_path)
        elif file_ext == '.docx':
            return self._process_docx(file_path)
    
    def _process_pdf(self, file_path: str) -> Dict:
        """Extract text from PDF"""
        logger.info(f"Processing PDF: {file_path}")
        
        try:
            reader = PdfReader(file_path)
            pages = []
            full_text = ""
            
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                pages.append({
                    "page_num": page_num + 1,
                    "text": text,
                    "char_count": len(text)
                })
                full_text += text + "\n"
            
            return {
                "success": True,
                "file_type": "pdf",
                "pages": len(pages),
                "text": full_text,
                "pages_detail": pages,
                "metadata": {
                    "author": reader.metadata.get('/Author', 'Unknown'),
                    "creator": reader.metadata.get('/Creator', 'Unknown'),
                    "producer": reader.metadata.get('/Producer', 'Unknown'),
                }
            }
            
        except Exception as e:
            logger.error(f"PDF processing failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "file_type": "pdf"
            }
    
    def _process_docx(self, file_path: str) -> Dict:
        """Extract text from Word document"""
        logger.info(f"Processing DOCX: {file_path}")
        
        try:
            doc = docx.Document(file_path)
            paragraphs = []
            full_text = ""
            
            for para_num, para in enumerate(doc.paragraphs):
                if para.text.strip():
                    paragraphs.append({
                        "para_num": para_num + 1,
                        "text": para.text,
                        "style": para.style.name if para.style else "Normal"
                    })
                    full_text += para.text + "\n"
            
            # Also extract tables
            tables = []
            for table_num, table in enumerate(doc.tables):
                table_data = []
                for row in table.rows:
                    row_data = [cell.text for cell in row.cells]
                    table_data.append(row_data)
                tables.append({
                    "table_num": table_num + 1,
                    "data": table_data
                })
            
            return {
                "success": True,
                "file_type": "docx",
                "paragraphs": len(paragraphs),
                "text": full_text,
                "paragraphs_detail": paragraphs,
                "tables": tables,
                "metadata": {
                    "core_properties": {
                        k: str(v) for k, v in doc.core_properties.__dict__.items() 
                        if v is not None
                    }
                }
            }
            
        except Exception as e:
            logger.error(f"DOCX processing failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "file_type": "docx"
            }
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize extracted text"""
        if not text:
            return ""
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        
        # Fix common PDF extraction issues
        text = text.replace('�', "'")  # Fix apostrophes
        text = text.replace('ﬀ', 'ff')  # Fix ligatures
        text = text.replace('ﬁ', 'fi')
        text = text.replace('ﬂ', 'fl')
        
        # Remove page numbers (common patterns)
        text = re.sub(r'\n\s*\d+\s*\n', '\n', text)
        text = re.sub(r'Page \d+ of \d+', '', text, flags=re.IGNORECASE)
        
        # Fix line breaks
        text = re.sub(r'(?<![.!?])\n', ' ', text)
        
        # Remove multiple newlines
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        return text.strip()
    
    def detect_questions(self, text: str) -> List[Dict]:
        """
        Detect question boundaries in ACCA exam answers
        
        Looks for patterns like:
        - "Requirement (a) - 4 marks"
        - "Question 1"
        - "(a) (4 marks)"
        """
        questions = []
        
        # Pattern 1: "Requirement (a) - 4 marks"
        pattern1 = r'(?:Requirement|Req)[\s.]*\(?([a-z])\)?[\s-]*(\d+)\s*marks?'
        
        # Pattern 2: "Question 1"
        pattern2 = r'Question\s+(\d+)'
        
        # Pattern 3: "(a) (4 marks)"
        pattern3 = r'\(([a-z])\)\s*\((\d+)\s*marks?\)'
        
        # Find all matches
        lines = text.split('\n')
        current_question = None
        question_text = []
        
        for i, line in enumerate(lines):
            # Check for question headers
            match1 = re.search(pattern1, line, re.IGNORECASE)
            match2 = re.search(pattern2, line, re.IGNORECASE)
            match3 = re.search(pattern3, line)
            
            if match1 or match2 or match3:
                # Save previous question if exists
                if current_question:
                    current_question['text'] = '\n'.join(question_text)
                    questions.append(current_question)
                
                # Start new question
                if match1:
                    current_question = {
                        'type': 'requirement',
                        'part': match1.group(1),
                        'marks': int(match1.group(2)),
                        'start_line': i,
                        'header': line.strip()
                    }
                elif match2:
                    current_question = {
                        'type': 'question',
                        'number': int(match2.group(1)),
                        'start_line': i,
                        'header': line.strip()
                    }
                elif match3:
                    current_question = {
                        'type': 'part',
                        'part': match3.group(1),
                        'marks': int(match3.group(2)),
                        'start_line': i,
                        'header': line.strip()
                    }
                
                question_text = []
            else:
                if current_question:
                    question_text.append(line)
        
        # Add last question
        if current_question and question_text:
            current_question['text'] = '\n'.join(question_text)
            questions.append(current_question)
        
        return questions
    
    def extract_marking_points(self, text: str) -> List[Dict]:
        """
        Extract individual marking points from marking scheme text
        
        Looks for:
        - 1 mark for X
        - ½ mark for Y
        - Award 1 mark if...
        """
        points = []
        
        # Pattern for explicit marks
        patterns = [
            r'(\d+)\s*mark\s*(?:for|if|when)\s*([^.\n]+)',
            r'([½¼¾])\s*mark\s*(?:for|if|when)\s*([^.\n]+)',
            r'Award\s*(\d+)\s*mark\s*(?:for|if|when)\s*([^.\n]+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                points.append({
                    'marks': self._parse_marks(match[0]),
                    'criteria': match[1].strip(),
                    'source': 'explicit'
                })
        
        # Also look for bullet points that might be marking points
        bullet_pattern = r'[•\-*]\s*([^.\n]+)'
        bullets = re.findall(bullet_pattern, text)
        
        for bullet in bullets:
            # Only add if it looks like a marking point
            if len(bullet.split()) > 3 and not points:
                points.append({
                    'marks': 1.0,  # Assume 1 mark if not specified
                    'criteria': bullet.strip(),
                    'source': 'bullet',
                    'confidence': 'low'
                })
        
        return points
    
    def _parse_marks(self, mark_str: str) -> float:
        """Convert mark string to float"""
        mark_str = mark_str.strip()
        if mark_str == '½':
            return 0.5
        elif mark_str == '¼':
            return 0.25
        elif mark_str == '¾':
            return 0.75
        else:
            try:
                return float(mark_str)
            except:
                return 1.0  # Default

    def extract_professional_marks(self, text: str) -> Dict:
        """
        Extract professional marks criteria
        
        Professional marks are usually for:
        - Presentation
        - Structure
        - Clarity
        - Professional language
        """
        criteria = {
            'presentation': 0,
            'structure': 0,
            'clarity': 0,
            'professional_language': 0,
            'total': 0
        }
        
        # Look for professional marks section
        prof_pattern = r'(?:professional|presentation|structure|clarity)[^.]*?(\d+)\s*marks?'
        matches = re.findall(prof_pattern, text, re.IGNORECASE)
        
        if matches:
            # Usually total professional marks are specified
            criteria['total'] = sum(int(m) for m in matches)
        else:
            # Default to 4 professional marks (common in ACCA)
            criteria['total'] = 4
        
        return criteria