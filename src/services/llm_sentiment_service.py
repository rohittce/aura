"""
LLM Sentiment Analysis Service
Uses online Llama models via APIs to analyze sentiment from user messages
Supports: Hugging Face Inference API, Replicate, OpenAI, and local models
"""

import os
from typing import Dict, Tuple, Optional
import logging
import requests
import json

logger = logging.getLogger(__name__)

try:
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import torch
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    logger.warning("transformers library not available. Local models disabled.")


class LLMSentimentService:
    """Service for sentiment analysis using online Llama models"""
    
    def __init__(self, model_path: Optional[str] = None):
        """
        Initialize LLM sentiment service.
        
        Args:
            model_path: Path to local Llama model (optional, for fallback)
        """
        self.model = None
        self.tokenizer = None
        self.device = "cuda" if TRANSFORMERS_AVAILABLE and torch.cuda.is_available() else "cpu" if TRANSFORMERS_AVAILABLE else None
        
        # Get model path from environment or use default
        if model_path is None:
            model_path = os.getenv("LLAMA_MODEL_PATH", "models/tinyllama")
        
        self.model_path = model_path
        
        # Cache for sentiment analysis (message hash -> result)
        self._sentiment_cache = {}
        self._cache_max_size = 1000
        
        # API Configuration
        self.api_provider = os.getenv("LLM_API_PROVIDER", "huggingface").lower()
        self.hf_api_key = os.getenv("HUGGINGFACE_API_KEY", "")
        self.hf_model = os.getenv("HF_MODEL", "TinyLlama/TinyLlama-1.1B-Chat-v1.0")
        self.replicate_api_key = os.getenv("REPLICATE_API_TOKEN", "")
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "")
        
        # Use online API by default, fallback to local if available
        self.use_online_api = os.getenv("USE_ONLINE_LLM", "true").lower() == "true"
        self.use_local_model = os.getenv("USE_LOCAL_LLM", "false").lower() == "true"
        
        # Initialize based on configuration
        if self.use_online_api:
            logger.info(f"Using online LLM API: {self.api_provider}")
        elif self.use_local_model and TRANSFORMERS_AVAILABLE:
            logger.info("Loading local Llama model...")
            self._load_model()
        else:
            logger.info("LLM sentiment disabled. Using fast rule-based analysis.")
    
    def _load_model(self):
        """Load the Llama model"""
        if not TRANSFORMERS_AVAILABLE:
            logger.warning("Transformers not available. Using fallback sentiment analysis.")
            return
        
        if not os.path.exists(self.model_path):
            logger.warning(f"Model path {self.model_path} not found. Using fallback sentiment analysis.")
            return
        
        try:
            logger.info(f"Loading Llama model from {self.model_path}...")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_path)
            self.model = AutoModelForCausalLM.from_pretrained(
                self.model_path,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                device_map="auto" if self.device == "cuda" else None,
                low_cpu_mem_usage=True
            )
            
            if self.device == "cpu":
                self.model = self.model.to(self.device)
            
            logger.info(f"✓ Model loaded successfully on {self.device}")
        except Exception as e:
            logger.error(f"Error loading model: {e}")
            logger.warning("Falling back to rule-based sentiment analysis")
            self.model = None
            self.tokenizer = None
    
    def analyze_sentiment(self, message: str, timeout: float = 5.0) -> Tuple[str, float, str]:
        """
        Analyze sentiment using online Llama API or local model with caching and timeout.
        
        Args:
            message: User's message
            timeout: Maximum time to wait for LLM (seconds), then fallback
            
        Returns:
            Tuple of (mood, confidence_score, explanation)
        """
        # Check cache first
        import hashlib
        import time
        message_hash = hashlib.md5(message.lower().strip().encode()).hexdigest()
        if message_hash in self._sentiment_cache:
            return self._sentiment_cache[message_hash]
        
        start_time = time.time()
        result = None
        
        # Try online API first
        if self.use_online_api:
            try:
                if self.api_provider == "huggingface":
                    result = self._analyze_with_hf_api(message, timeout)
                elif self.api_provider == "replicate":
                    result = self._analyze_with_replicate_api(message, timeout)
                elif self.api_provider == "openai":
                    result = self._analyze_with_openai_api(message, timeout)
                else:
                    logger.warning(f"Unknown API provider: {self.api_provider}")
            except Exception as e:
                logger.error(f"Online API error: {e}")
                result = None
        
        # Fallback to local model if online API failed
        if result is None and self.use_local_model and self.model is not None and self.tokenizer is not None:
            try:
                elapsed = time.time() - start_time
                remaining_timeout = max(0, timeout - elapsed)
                if remaining_timeout > 0:
                    result = self._analyze_with_llm_fast(message)
            except Exception as e:
                logger.error(f"Local model error: {e}")
                result = None
        
        # Final fallback to rule-based
        if result is None:
            result = self._fallback_sentiment_analysis(message)
        
        self._cache_result(message_hash, result)
        return result
    
    def _analyze_with_hf_api(self, message: str, timeout: float) -> Optional[Tuple[str, float, str]]:
        """Analyze sentiment using Hugging Face Inference API"""
        if not self.hf_api_key:
            logger.warning("Hugging Face API key not set. Set HUGGINGFACE_API_KEY environment variable.")
            return None
        
        prompt = f'Analyze the sentiment of this message and respond with only one word: happy, sad, angry, calm, energetic, tired, anxious, romantic, nostalgic, or focused.\n\nMessage: "{message}"\nSentiment:'
        
        try:
            api_url = f"https://api-inference.huggingface.co/models/{self.hf_model}"
            headers = {"Authorization": f"Bearer {self.hf_api_key}"}
            
            payload = {
                "inputs": prompt,
                "parameters": {
                    "max_new_tokens": 10,
                    "temperature": 0.1,
                    "return_full_text": False
                },
                "options": {
                    "wait_for_model": True
                }
            }
            
            response = requests.post(api_url, headers=headers, json=payload, timeout=timeout)
            
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    generated_text = result[0].get("generated_text", "").strip().lower()
                    
                    # Extract mood
                    valid_moods = ["happy", "sad", "angry", "calm", "energetic", "tired", "anxious", "romantic", "nostalgic", "focused"]
                    for mood in valid_moods:
                        if mood in generated_text:
                            return mood, 0.8, f"Analyzed by Hugging Face API ({self.hf_model})"
                    
                    # Default if no match
                    return "calm", 0.6, f"Analyzed by Hugging Face API ({self.hf_model})"
            else:
                logger.warning(f"HF API error: {response.status_code} - {response.text}")
                return None
                
        except requests.Timeout:
            logger.warning("Hugging Face API timeout")
            return None
        except Exception as e:
            logger.error(f"Hugging Face API error: {e}")
            return None
    
    def _analyze_with_replicate_api(self, message: str, timeout: float) -> Optional[Tuple[str, float, str]]:
        """Analyze sentiment using Replicate API"""
        if not self.replicate_api_key:
            logger.warning("Replicate API token not set. Set REPLICATE_API_TOKEN environment variable.")
            return None
        
        try:
            try:
                import replicate
            except ImportError:
                logger.warning("Replicate library not installed. Install with: pip install replicate")
                return None
            
            prompt = f'Analyze sentiment: "{message}"\nRespond with one word: happy, sad, angry, calm, energetic, tired, anxious, romantic, nostalgic, or focused.'
            
            output = replicate.run(
                "meta/llama-2-7b-chat",
                input={
                    "prompt": prompt,
                    "max_length": 20,
                    "temperature": 0.1
                }
            )
            
            result_text = "".join(output).strip().lower()
            valid_moods = ["happy", "sad", "angry", "calm", "energetic", "tired", "anxious", "romantic", "nostalgic", "focused"]
            for mood in valid_moods:
                if mood in result_text:
                    return mood, 0.8, "Analyzed by Replicate API"
            
            return "calm", 0.6, "Analyzed by Replicate API"
            
        except ImportError:
            logger.warning("Replicate library not installed. Install with: pip install replicate")
            return None
        except Exception as e:
            logger.error(f"Replicate API error: {e}")
            return None
    
    def _analyze_with_openai_api(self, message: str, timeout: float) -> Optional[Tuple[str, float, str]]:
        """Analyze sentiment using OpenAI API"""
        if not self.openai_api_key:
            logger.warning("OpenAI API key not set. Set OPENAI_API_KEY environment variable.")
            return None
        
        try:
            prompt = f'Analyze the sentiment of this message and respond with only one word: happy, sad, angry, calm, energetic, tired, anxious, romantic, nostalgic, or focused.\n\nMessage: "{message}"\nSentiment:'
            
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openai_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 10,
                    "temperature": 0.1
                },
                timeout=timeout
            )
            
            if response.status_code == 200:
                result = response.json()
                mood_text = result["choices"][0]["message"]["content"].strip().lower()
                
                valid_moods = ["happy", "sad", "angry", "calm", "energetic", "tired", "anxious", "romantic", "nostalgic", "focused"]
                for mood in valid_moods:
                    if mood in mood_text:
                        return mood, 0.9, "Analyzed by OpenAI API"
                
                return "calm", 0.7, "Analyzed by OpenAI API"
            else:
                logger.warning(f"OpenAI API error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return None
    
    def _analyze_with_llm_fast(self, message: str) -> Tuple[str, float, str]:
        """Fast LLM analysis with optimized settings"""
        # Simplified prompt for faster processing
        prompt = f'Message: "{message}"\nMood (happy/sad/angry/calm/energetic/tired/anxious/romantic/nostalgic/focused):'
        
        try:
            # Tokenize with shorter max length
            inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=256)
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            
            # Generate with minimal tokens
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=20,  # Very short response
                    temperature=0.1,  # Very deterministic
                    do_sample=False,  # Greedy
                    pad_token_id=self.tokenizer.eos_token_id,
                    num_beams=1,
                    early_stopping=True
                )
            
            # Decode and extract mood
            response = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
            response_text = response[len(prompt):].strip().lower()
            
            # Quick mood extraction
            valid_moods = ["happy", "sad", "angry", "calm", "energetic", "tired", "anxious", "romantic", "nostalgic", "focused"]
            for mood in valid_moods:
                if mood in response_text:
                    return mood, 0.7, "Analyzed by LLM"
            
            # Fallback if no mood found
            return "calm", 0.5, "Analyzed by LLM"
            
        except Exception as e:
            logger.error(f"LLM sentiment analysis error: {e}")
            return self._fallback_sentiment_analysis(message)
    
    def _extract_mood_from_text(self, text: str) -> str:
        """Extract mood from LLM text response"""
        text_lower = text.lower()
        
        mood_keywords = {
            "happy": ["happy", "joy", "positive", "good", "great"],
            "sad": ["sad", "depressed", "down", "unhappy"],
            "angry": ["angry", "mad", "furious", "annoyed"],
            "calm": ["calm", "peaceful", "relaxed"],
            "energetic": ["energetic", "pumped", "active"],
            "tired": ["tired", "exhausted", "sleepy"],
            "anxious": ["anxious", "worried", "stressed"],
            "romantic": ["romantic", "love"],
            "nostalgic": ["nostalgic", "memories"],
            "focused": ["focused", "concentrated"]
        }
        
        for mood, keywords in mood_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                return mood
        
        return "calm"
    
    def _fallback_sentiment_analysis(self, message: str) -> Tuple[str, float, str]:
        """Fallback rule-based sentiment analysis"""
        message_lower = message.lower()
        
        sentiment_keywords = {
            "happy": ["happy", "great", "awesome", "excited", "joy", "wonderful", "amazing", "fantastic", "love", "good", "nice", "glad", "pleased"],
            "sad": ["sad", "depressed", "down", "upset", "unhappy", "disappointed", "hurt", "lonely", "miserable", "sorrow"],
            "angry": ["angry", "mad", "furious", "annoyed", "irritated", "frustrated", "rage", "hate"],
            "calm": ["calm", "peaceful", "relaxed", "chill", "serene", "tranquil", "zen", "quiet"],
            "energetic": ["energetic", "pumped", "motivated", "active", "workout", "exercise", "gym", "running"],
            "tired": ["tired", "exhausted", "sleepy", "drained", "worn out", "fatigued"],
            "anxious": ["anxious", "worried", "stressed", "nervous", "overwhelmed", "pressure", "tense"],
            "romantic": ["romantic", "love", "dating", "relationship", "partner", "crush", "heart"],
            "nostalgic": ["nostalgic", "memories", "remember", "past", "childhood", "old times"],
            "focused": ["focused", "studying", "work", "concentrate", "productive", "busy", "task"]
        }
        
        sentiment_scores = {}
        for mood, keywords in sentiment_keywords.items():
            score = sum(1 for keyword in keywords if keyword in message_lower)
            if score > 0:
                sentiment_scores[mood] = score
        
        if not sentiment_scores:
            return "calm", 0.3, "Neutral sentiment detected"
        
        dominant_mood = max(sentiment_scores.items(), key=lambda x: x[1])[0]
        max_score = sentiment_scores[dominant_mood]
        total_keywords = sum(sentiment_scores.values())
        confidence = min(max_score / total_keywords, 1.0)
        
        return dominant_mood, confidence, f"Detected {dominant_mood} sentiment"
    
    def _cache_result(self, message_hash: str, result: Tuple[str, float, str]):
        """Cache sentiment analysis result"""
        # Simple LRU: remove oldest if cache full
        if len(self._sentiment_cache) >= self._cache_max_size:
            # Remove first item (oldest)
            first_key = next(iter(self._sentiment_cache))
            del self._sentiment_cache[first_key]
        
        self._sentiment_cache[message_hash] = result


# Singleton instance
_llm_sentiment_service = None

def get_llm_sentiment_service() -> LLMSentimentService:
    """Get singleton instance of LLMSentimentService"""
    global _llm_sentiment_service
    if _llm_sentiment_service is None:
        _llm_sentiment_service = LLMSentimentService()
    return _llm_sentiment_service

