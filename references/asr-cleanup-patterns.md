# ASR Cleanup Patterns (Chinese Audio)

Reference replacement map for cleaning raw FunASR / paraformer output from Chinese speech, especially tech podcasts, Twitter Spaces, and interview recordings.

## Usage

Apply these replacements **in order** via `str.replace()` or regex substitution before paragraph reassembly. The map is split into semantic categories so you can subset by context.

---

## 1. Repeated Filler Loops (must remove aggressively)

These appear when a speaker stutters or the ASR hallucinates repetition:

| Pattern | Action |
|---------|--------|
| `(我先说一下，?)+[。，]?\n` | Remove entire line |
| `(我先说一下，?)+` | Remove all repetitions |
| `(嗯，?)+` | Collapse to single 嗯 |
| `(哦，?)+` | Collapse to single 哦 |
| `(那个，?)+` | Collapse to single 那个 |
| `(the\s+)+` | Remove (English filler noise) |

---

## 2. Tech Term Mistranscriptions

Common in crypto / AI / Web3 Chinese Spaces:

| ASR Error | Correction | Context |
|-----------|------------|---------|
| `龙虾` / `大龙虾` / `小龙虾` | `Agent` | AI agent |
| `引擎` | `Agent` | In AI contexts |
| `OPEN CLOUD` / `open cloud` / `OPENCLOUD` | `OpenCode` | OpenCode / OpenCode Workspace |
| `color code` / `cloud code` / `C loud code` / `克劳克劳迪` | `Claude Code` | Anthropic's coding tool |
| `Cloudy` / `cloudy` | `Claude` | Anthropic's model |
| `克劳德代码` | `Claude Code` | |
| `S40 21` / `S四零二` / `叉四零二` / `X零二` / `S402` / `S 6. 2` / `S 4. 2` / `S02` / `S10 2` | `x402` | HTTP 402 payment protocol |
| `查斯利亚` / `查斯尼奥` | `x402` | |
| `MMP` / `MMPB` / `MAPP` / `MMPP` | `MPP` | Stripe's Multi-Party Payments |
| `TEMPO` / `TEMPLE` / `TEMPLETEMPLE` | `Tempo` | Stripe's internal settlement network |
| `STRIP` / `STRIPES` / `script` / `Script` / `STRIKE` / `STREP` / `STRAP` | `Stripe` | Payment processor |
| `CON BASE` / `CONBASED` / `康贝斯` / `COINBASED` | `Coinbase` | Exchange & protocol |
| `ITF` | `IETF` | Internet standards body |
| `WEBCODING` | `Web Coding` | Web-based coding |
| `WEBTO` | `Web2` | Traditional web |
| `AGING` | `Agent` | ASR slur |
| `AIAGING` | `AI Agent` | |
| `AGENTMAJORS` / `agent matches` / `agent match` | `Agent Matrix` | Agent orchestration concept |
| `FILIATOR` / `FACILITATE` / `FACILITY` / `facility a` | `Facilitator` | x402 middleware role |
| `CLANFAIR` / `CLOUDFAIR` | `Cloudflare` | CDN / edge computing |
| `EUA` | `EOA` | Externally Owned Account (wallet) |
| `EQUITANTAL` | `credentials` | ASR hallucination |
| `PAM` | `Payment` | |
| `GS 4. 2` / `S 40 28` | `x402` | Protocol reference |
| `felici t` / `file` | `Facilitator` | |
| `mails tiff` | `MailShift` | Product name |
| `chicks点com` / `chicks.com` | `chix.com` | Website |
| `DEMO` | `Demo` | |
| `ON BODY` / `ON BOARDING` / `ON?\nBoarding` | `onboarding` | |
| `MASSADOPTION` / `MASSIVEOPTION` | `mass adoption` | |

---

## 3. Speaker Name Mistranscriptions

| ASR Error | Correction |
|-----------|------------|
| `宁宁` / `宁老师` / `李老师` / `李老师在` | `倪倪` / `倪老师` |
| `韦大伟` / `韦莱维` / `韦乐伟` / `维莱瑞尔` / `维莱瑞亚` / `弗莱瑞亚` / `未来薇娅` / `韦达瑞亚` | `Veleria` |
| `西皮` / `西比` / `西雨` / `C P ` / `CBA` / `CV` | `CP` |
| `郭玉` / `郭伟` | `郭宇` |
| `了了君` | (remove or genericize) |

---

## 4. Organization & Product Names

| ASR Error | Correction |
|-----------|------------|
| `ESPANDER` / `ESPINDA` / `IS PANDA` | `Espander` |
| `TANGRAMBA` | `Tangram` |
| `DARYA` | `Darya` |

---

## 5. General Cleanup Rules

1. **Paragraph breaks**: Replace `\n{3,}` with `\n\n`.
2. **Low-diversity lines**: If `len(set(line)) < 5 and len(line) > 20`, drop the line (usually pure punctuation or repeated single characters).
3. **Excessive whitespace**: Strip leading/trailing spaces on every line; collapse multiple spaces to one.
4. **Partial English noise**: Remove standalone English articles (`a`, `an`, `the`) that appear mid-Chinese sentence when they add no meaning.

---

## Example Python Snippet

```python
import re

replacements = {
    "龙虾": "Agent",
    "大龙虾": "Agent",
    "小龙虾": "Agent",
    "OPEN CLOUD": "OpenCode",
    # ... add more from tables above
}

def clean_asr(text: str) -> str:
    # Remove filler loops
    text = re.sub(r"(我先说一下，?)+[。，]?\n", "", text)
    text = re.sub(r"(我先说一下，?)+", "", text)
    
    # Apply replacements
    for old, new in replacements.items():
        text = text.replace(old, new)
    
    # Normalize whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    
    # Filter low-diversity paragraphs
    paragraphs = text.split("\n\n")
    clean = []
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if len(set(p)) < 5 and len(p) > 20:
            continue
        clean.append(p)
    
    return "\n\n".join(clean)
```
