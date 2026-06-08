from deepseek import DeepSeekModel

class AIConfig:
    def __init__(self):
        self.model = DeepSeekModel()
        self.model.load_local_model("ścieżka/do/zainstalowanego/modelu")
        
    def generate_response(self, prompt: str) -> str:
        return self.model.generate(
            prompt=prompt,
            max_tokens=500,
            temperature=0.7
        )