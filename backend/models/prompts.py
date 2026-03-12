"""
Question-Specific Prompt Builders
"""

import json
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class PromptBuilder:
    """Build prompts for different question types"""
    
    @staticmethod
    def build_audit_risk_prompt(
        question_text: str,
        student_answer: str,
        marking_rules: List[Dict],
        examiner_guidance: List[str],
        max_marks: float,
        context: Optional[Dict] = None
    ) -> str:
        """Build prompt for audit risk questions"""
        
        # Format marking rules
        rules_text = ""
        for i, rule in enumerate(marking_rules, 1):
            rules_text += f"\n{i}. {rule['text']}"
            if rule.get('marks'):
                rules_text += f" (Marks: {rule['marks']})"
        
        # Format examiner guidance
        guidance_text = ""
        for i, guidance in enumerate(examiner_guidance, 1):
            guidance_text += f"\n{i}. {guidance[:200]}..."  # Truncate long guidance
        
        prompt = f"""You are an expert ACCA AA marker. You must mark this audit risk question STRICTLY according to the marking scheme.

QUESTION:
{question_text}

MAXIMUM MARKS: {max_marks}

MARKING SCHEME (Reference only - use these rules):
{rules_text}

EXAMINER GUIDANCE (Common mistakes and tips):
{guidance_text}

STUDENT ANSWER:
{student_answer}

INSTRUCTIONS:
1. For audit risk questions, marks are allocated as:
   - ½ mark for IDENTIFYING a specific risk from the scenario
   - ½ mark for EXPLAINING why it's a risk (with assertion and financial impact)
   - 1 mark for AUDITOR RESPONSE (practical, specific action)

2. Common mistakes to avoid awarding marks for:
   - Generic risks not specific to the scenario
   - Explanations without assertions (valuation, completeness, etc.)
   - Vague responses like "discuss with management"
   - Management responses instead of auditor responses

3. Professional marks (up to 2 marks) are for:
   - Structure and presentation (0.5)
   - Correct terminology (0.5)  
   - Practical application (0.5)
   - Commercial awareness (0.5)

4. You MUST respond with valid JSON in this exact format:
{{
    "total_marks": 0.0,
    "max_marks": {max_marks},
    "question_marks": [
        {{
            "point": "Description of marking point",
            "awarded": 0.5,
            "explanation": "Why this mark was awarded"
        }}
    ],
    "professional_marks": {{
        "structure": 0.5,
        "terminology": 0.5,
        "practicality": 0.5,
        "commercial_awareness": 0.5
    }},
    "feedback": "Overall feedback for student",
    "citations": ["Reference to ISA or marking scheme"]
}}

Now, mark this answer and return ONLY the JSON response:"""
        
        return prompt
    
    @staticmethod
    def build_ethical_threats_prompt(
        question_text: str,
        student_answer: str,
        marking_rules: List[Dict],
        examiner_guidance: List[str],
        max_marks: float,
        context: Optional[Dict] = None
    ) -> str:
        """Build prompt for ethical threats questions"""
        
        prompt = f"""You are an expert ACCA AA marker. Mark this ethical threats question.

QUESTION:
{question_text}

MAXIMUM MARKS: {max_marks}

STUDENT ANSWER:
{student_answer}

INSTRUCTIONS:
1. For ethical threats, marks are allocated as:
   - ½ mark for IDENTIFYING the threat type (self-interest, familiarity, etc.)
   - ½ mark for EXPLAINING the implication
   - 1 mark for SAFEGUARD (practical action)

2. Common threat types:
   - Self-interest
   - Self-review  
   - Advocacy
   - Familiarity
   - Intimidation

3. Safeguards must be ACTIONS, not objectives:
   - ✓ "Rotate the audit manager off the engagement"
   - ✗ "Ensure independence is maintained"

Respond with JSON in the same format as audit risk questions."""
        
        return prompt
    
    @staticmethod
    def build_procedures_prompt(
        question_text: str,
        student_answer: str,
        marking_rules: List[Dict],
        examiner_guidance: List[str],
        max_marks: float,
        context: Optional[Dict] = None
    ) -> str:
        """Build prompt for substantive procedures questions"""
        
        prompt = f"""You are an expert ACCA AA marker. Mark this substantive procedures question.

QUESTION:
{question_text}

MAXIMUM MARKS: {max_marks}

STUDENT ANSWER:
{student_answer}

INSTRUCTIONS:
1. Each well-described procedure = 1 mark
2. Procedures must be:
   - SPECIFIC (not vague)
   - PRACTICAL (auditor can actually do it)
   - COMPLETE (includes source document and what to test)

3. Example of good procedure:
   "Select a sample of sales invoices and agree the amounts to the sales ledger to test accuracy."

Respond with JSON in the same format as audit risk questions."""
        
        return prompt

# Singleton instance
prompt_builder = PromptBuilder()