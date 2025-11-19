# LLM Strategy & Model Routing

**For complete details, see `holocene_design.md` lines 189-256.**

---

## Provider: NanoGPT Subscription

- **Cost:** $8/month
- **Quota:** 2,000 prompts/day (60,000/month)
- **Models:** 200+ open-source models included
- **Privacy:** No data storage, local-first design

---

## Model Routing

Specialized LLMs for different task types:

```python
class ModelRouter:
    MODELS = {
        'primary': 'deepseek-v3',           # 128K context
        'coding': 'qwen-3-coder',           # Specialized for code
        'math': 'math-specialist',          # Calculations
        'reasoning': 'deepseek-r1',         # Step-by-step thinking
        'verification': 'hermes-4-large',   # Different architecture
        'canary': 'llama-3b',              # Lightweight injection detection
    }
```

**Context Windows:**
- DeepSeek V3: 128K tokens (~96k words)
- Qwen 3 Coder: 128K tokens
- Llama 3B (canary): 8K tokens

---

## Model-Specific Use Cases

**DeepSeek V3 (Primary):**
- Daily synthesis and analysis
- Complex multi-step tasks
- General assistance
- Pattern detection

**Qwen 3 Coder:**
- Code generation/review
- GGR/wabisabi/Pollywog development
- Technical documentation
- Often better than DS V3 for coding

**DeepSeek R1:**
- Complex reasoning chains
- Debugging logic problems
- Step-by-step explanations

**Hermes 4 Large:**
- Summary verification (different from DS V3)
- Alternative perspectives
- Cross-checking DS V3 outputs

**Llama 3B (Canary):**
- Lightweight injection detection
- Content verification
- Fast pre-screening

---

**Last Updated:** 2025-11-17
**Implementation:** `src/holocene/llm/` (planned)
