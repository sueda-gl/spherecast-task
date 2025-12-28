"""
Generic LLM Client for API calls.

Simple wrapper around OpenAI API with support for text and vision inputs.
"""

import os
from typing import Optional, Union
from pathlib import Path
import base64
import json

import openai


class LLMClient:
    """Generic client for LLM API calls."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        temperature: float = 0.0,
    ):
        """
        Initialize LLM client.
        
        Args:
            api_key: API key (defaults to OPENAI_API_KEY env var)
            model: Model to use
            temperature: Temperature for generation
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("API key required. Set OPENAI_API_KEY env var or pass api_key")
        
        self.model = model
        self.temperature = temperature
        self.client = openai.OpenAI(api_key=self.api_key)
    
    def call_with_image(
        self,
        prompt: str,
        image_path: Union[str, Path],
        json_mode: bool = True
    ) -> dict:
        """
        Call LLM with an image/document input.
        
        Args:
            prompt: System prompt
            image_path: Path to image or document file
            json_mode: Whether to enforce JSON output
        
        Returns:
            LLM response (parsed as JSON if json_mode=True)
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"File not found: {image_path}")
        
        # Encode image as base64
        encoded_image = self._encode_file(image_path)
        media_type = self._get_media_type(image_path)
        
        # Build messages with image
        messages = [
            {"role": "system", "content": prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{encoded_image}"
                        }
                    }
                ]
            }
        ]
        
        return self._make_api_call(messages, json_mode)
    
    def call_with_text(
        self,
        prompt: str,
        text: str,
        json_mode: bool = True
    ) -> dict:
        """
        Call LLM with text input.
        
        Args:
            prompt: System prompt
            text: Text input
            json_mode: Whether to enforce JSON output
        
        Returns:
            LLM response (parsed as JSON if json_mode=True)
        """
        # Build messages with text
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ]
        
        return self._make_api_call(messages, json_mode)
    
    def _make_api_call(self, messages: list, json_mode: bool) -> dict:
        """Make the actual API call."""
        try:
            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
            }
            
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            
            response = self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            
            # Parse JSON if requested
            if json_mode:
                try:
                    # Clean content - remove leading/trailing whitespace and newlines
                    cleaned_content = content.strip()
                    
                    # Remove markdown code blocks if present
                    if cleaned_content.startswith("```"):
                        # Find the first newline after opening ```
                        first_newline = cleaned_content.find("\n")
                        if first_newline != -1:
                            cleaned_content = cleaned_content[first_newline + 1:]
                        # Remove closing ```
                        if cleaned_content.endswith("```"):
                            cleaned_content = cleaned_content[:-3].rstrip()
                    
                    return json.loads(cleaned_content)
                except json.JSONDecodeError as je:
                    # Log the problematic content for debugging
                    print(f"\n{'='*60}")
                    print(f"JSON PARSE ERROR")
                    print(f"{'='*60}")
                    print(f"Error: {je}")
                    print(f"\nContent received (first 1000 chars):")
                    print(content[:1000])
                    print(f"{'='*60}\n")
                    raise RuntimeError(f"Failed to parse JSON response: {je}. Content preview: {content[:200]}")
            else:
                return {"response": content}
            
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {e}")
    
    def _encode_file(self, file_path: Path) -> str:
        """Encode file as base64 string."""
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    
    def _get_media_type(self, file_path: Path) -> str:
        """Determine MIME type from file extension."""
        extension = file_path.suffix.lower()
        
        media_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".pdf": "application/pdf",
        }
        
        return media_types.get(extension, "image/jpeg")

