# Competitive & Ecosystem Landscape

> Every relevant player, model, API, and dataset — each with our stance:
> **REUSE** (consume it), **BUILD-ON** (start from it, replace later), **COMPETE** (we beat it),
> **IGNORE** (not our fight), **COMPLEMENT** (different problem, plays well with us).
>
> Part of the TruthPixel doc suite: [ARCHITECTURE.md](ARCHITECTURE.md) · [ML_PLAN.md](ML_PLAN.md) ·
> [AGENTS.md](AGENTS.md) · [ROADMAP.md](ROADMAP.md)

## 1. Commercial tools & platforms

| Player | What they do | Stance | Why |
|---|---|---|---|
| [Sightengine AI detection](https://sightengine.com/detect-ai-generated-images) | API for AI-image detection | **REUSE → replace** | Day-1 signal for L1 second opinion; drop later to cut per-call cost |
| [Sightengine Recapture](https://sightengine.com/docs/image-recapture-detection) | Detects photos-of-screens, prints, recaptures | **REUSE → replace** | Our L3 day-1 backbone — the screenshot-evasion counter. Replace with own CNN in Phase 2 |
| [Reality Defender](https://www.realitydefender.com/) | Enterprise deepfake/media detection | **IGNORE (avoid head-on)** | General media/deepfake, big-enterprise buyer. We're vertical: returns workflow |
| [Hive AI](https://thehive.ai/) | Content-moderation + AI detection APIs | **IGNORE / optional signal** | Moderation-focused; could be a paid extra L1 opinion, not a rival in our vertical |
| [Sensity AI](https://sensity.ai/) | Deepfake detection platform | **IGNORE** | Identity/KYC/deepfake video focus, not product-photo fraud |
| [Truepic](https://www.truepic.com/) | Trusted **capture-time** verification SDK | **COMPLEMENT** | They prove authenticity at capture; we verify arbitrary post-hoc uploads. Could even integrate |
| [Adobe Content Credentials Verify](https://contentcredentials.org/verify) | C2PA verification web tool | **REUSE (concept)** | We run the same check programmatically via c2patool as an L4 signal |
| [Content Authenticity Initiative](https://contentauthenticity.org/) | Provenance industry initiative | **REUSE (standard)** | Follow the standard, join later for credibility |
| [C2PA](https://c2pa.org/) | Provenance metadata standard | **REUSE** | Consume, never build our own provenance standard |
| [Google SynthID](https://deepmind.google/technologies/synthid/) | Invisible watermark for AI content | **REUSE** | Verify-only signal in L4; most robust-to-screenshot provenance signal that exists |
| [OpenAI Verify](https://openai.com/research/verify/) | OpenAI image provenance check | **REUSE** | Same — one L4 sub-check |
| [AI or Not](https://www.aiornot.com/) | Consumer "is it AI?" checker | **COMPETE (easily)** | No workflow, no localization, no e-commerce context, binary answer. Our report beats it |
| [Deepware Scanner](https://scanner.deepware.ai/) | Deepfake **video** scanner | **IGNORE** | Video deepfakes ≠ our problem (Phase 3+ maybe) |
| [TrueMedia.org](https://www.truemedia.org/) | Political/media misinformation detection | **IGNORE** | Different mission and buyer entirely |

**Net read:** nobody combines AI-gen + edit forensics + recapture + provenance + **seller-listing
cross-check** in a returns-review workflow. The vertical fusion is open ground.

## 2. Open-source AI-generation detectors (Layer 1 candidates)

| Model | Stance | Why |
|---|---|---|
| [UniversalFakeDetect](https://github.com/WisconsinAIVision/UniversalFakeDetect) | **BUILD-ON (primary)** | CLIP-feature + linear head; best cross-generator generalization; our L1 recipe |
| [NPR](https://github.com/chuangchuangtan/NPR-DeepfakeDetection) | **BUILD-ON (secondary)** | Tiny CNN on upsampling artifacts; cheap second opinion, trainable on one GPU |
| [DIRE](https://github.com/ZhendongWang6/DIRE) | **IGNORE (for now)** | Diffusion-reconstruction error is strong but inference-expensive (needs a diffusion model per check) |
| [CNNDetection](https://github.com/PeterWang512/CNNDetection) | **REUSE (baseline)** | Classic baseline to benchmark against, plus its ForenSynths dataset |
| [FreqNet](https://github.com/chuangchuangtan/FreqNet-DeepfakeDetection) | **REUSE (eval)** | Frequency-domain comparison point; frequency features die under recompression — verify that claim |
| [GramNet](https://github.com/liuzhengzhe/Global_Texture_Enhancement_for_Fake_Face_Detection_in_the-Wild) | **IGNORE** | Face-centric texture model; we're product photos |
| [LGrad](https://github.com/aimagelab/LGrad) | **REUSE (eval)** | Comparison baseline |
| [RINE](https://github.com/megvii-research/RINE) | **REUSE (eval)** | Comparison baseline (pretrained-representation approach, like ours) |
| [CLIP](https://github.com/openai/CLIP) / [OpenCLIP](https://github.com/mlfoundations/open_clip) | **REUSE (backbone)** | Frozen feature extractor for L1 head + L5 similarity |

The models above are research repos (run-it-yourself). The table below is what we **actually
wired**: pretrained detectors served live on the **HF Inference API**, so L1 works with zero
training and zero GPU hosting. We call an *ensemble* of them (independent architectures →
uncorrelated errors → better on unseen generators). Implementation: `backend/app/hf_inference.py`.
License is load-bearing for a startup — only commercial-safe ones are in the default set.

| HF model | Arch | Downloads | License | Stance |
|---|---|---|---|---|
| [Ateeqq/ai-vs-human-image-detector](https://hf.co/Ateeqq/ai-vs-human-image-detector) | SigLIP | 300K | Apache-2.0 | **USE — default ensemble member** |
| [Nahrawy/AIorNot](https://hf.co/Nahrawy/AIorNot) | Swin | 63K | Apache-2.0 | **USE — default ensemble member** |
| [umm-maybe/AI-image-detector](https://hf.co/umm-maybe/AI-image-detector) | ViT | 451K | CC-BY-4.0 | **OPTIONAL** — commercial OK *with attribution*; add if it improves ensemble |
| [haywoodsloan/ai-image-detector-deploy](https://hf.co/haywoodsloan/ai-image-detector-deploy) | SwinV2 | 219K | none stated | **EVAL** — no explicit license; don't ship until clarified |
| [Organika/sdxl-detector](https://hf.co/Organika/sdxl-detector) | Swin | 682K | **CC-BY-NC-3.0** | **EVAL/DEMO ONLY** — non-commercial; never in the commercial default set |

## 3. Open-source manipulation-forensics models (Layer 2 candidates)

| Model | Stance | Why |
|---|---|---|
| [TruFor](https://github.com/grip-unina/TruFor) | **REUSE (primary)** | Pretrained forgery localization + integrity score + heatmap — demo gold, inference only |
| [MVSS-Net](https://github.com/dong03/MVSS-Net) | **REUSE (alternate)** | Fallback/ensemble option for splicing/copy-move |
| [CAT-Net](https://github.com/mjkwon2021/CAT-Net) | **REUSE (alternate)** | Compression-artifact tracing — good on JPEG-recompressed images (screenshot-relevant) |
| [PSCC-Net](https://github.com/proteus1991/PSCC-Net) | **IGNORE** | Covered by the three above |
| [ManTraNet](https://github.com/ISICV/ManTraNet) | **IGNORE** | Older, superseded by TruFor |
| [Noiseprint](https://github.com/grip-unina/noiseprint) | **REUSE (advanced)** | Camera-noise fingerprinting for Phase 2 consistency analysis |
| [LoMa](https://github.com/multimediaFor/LoMa) | **REUSE (eval)** | Research comparison only |

## 4. Recapture / screenshot detection (Layer 3)

| Tool | Stance | Why |
|---|---|---|
| Sightengine Recapture API | **REUSE → replace** | Only mature commercial option; day-1 signal |
| Sightengine Image-Type API | **REUSE (cheap pre-filter)** | Screenshot/graphic/photo triage before deep analysis |
| Custom recapture CNN | **BUILD (Phase 2)** | Small classifier: direct-capture vs screenshot vs photo-of-screen vs print-recapture; moiré/screen-grid/glare features. Own dataset (see ML_PLAN) |

## 5. Metadata / provenance tooling (Layer 4)

| Tool | Stance |
|---|---|
| [ExifTool](https://exiftool.org/) / [piexif](https://github.com/hMatoba/Piexif) | **REUSE** — EXIF extraction |
| [c2patool](https://github.com/contentauth/c2patool) / [c2pa-python](https://github.com/contentauth/c2pa-python) | **REUSE** — C2PA verification |
| SynthID / OpenAI Verify | **REUSE** — watermark/provenance checks |

Weighting rule everywhere: **absent metadata = neutral**, only positive traces score.

## 6. Similarity / product matching (Layer 5)

| Tool | Stance | Why |
|---|---|---|
| [DINOv2](https://github.com/facebookresearch/dinov2) | **REUSE (primary embed)** | Best self-supervised features for same-product matching |
| [OpenCLIP](https://github.com/mlfoundations/open_clip) | **REUSE (secondary)** | Shared backbone with L1 — one model, two jobs |
| [Qdrant](https://github.com/qdrant/qdrant) | **REUSE (vector DB)** | Simple to self-host, good filtering; chosen over Milvus (heavy) and Chroma (toy-ish) |
| [FAISS](https://github.com/facebookresearch/faiss) | **REUSE (in-process alt)** | Fine for MVP before Qdrant is up |
| [TinEye API](https://tineye.com/developers) / [SerpAPI Google Lens](https://serpapi.com/google-lens-api) | **REUSE** | Reverse-image search for reused/stolen damage photos |
| [Bing Visual Search](https://www.microsoft.com/en-us/bing/apis/bing-visual-search-api) | **IGNORE** | Retiring/unstable API line; SerpAPI covers it |

## 7. Third-party APIs summary (what we'd actually pay for)

| API | Used in | When |
|---|---|---|
| Sightengine (AI-gen + recapture + image-type) | L1 opinion, L3 | Phase 0 → replaced Phase 2 |
| TinEye or SerpAPI Lens | L5 reverse-image | Phase 1 |
| Vertex AI (Gemini) | Agent pass + report writer | Phase 0+, cost-gated; existing $1,000 credit may cover this but is scoped to GenAI App Builder — verify before relying on it, see AGENTS.md |
| Google Vision | OCR on labels/receipts (later idea) | Phase 2+ |

## 8. Datasets

### AI-generated (L1)
| Dataset | Role |
|---|---|
| [GenImage](https://github.com/GenImage-Dataset/GenImage) | **Primary training** — 1M+, 8 generators; enables held-out-generator eval |
| [CIFAKE](https://www.kaggle.com/datasets/birdy654/cifake-real-and-ai-generated-synthetic-images) | Quick baseline sanity check |
| [DiffusionDB](https://github.com/poloclub/diffusiondb) | Extra SD-generated volume |
| [ForenSynths](https://github.com/PeterWang512/CNNDetection) | GAN-era coverage (older generators) |
| [AIGCDetectBenchmark](https://github.com/Ekko-zn/AIGCDetectBenchmark) | Standardized eval harness |
| UniversalFakeDetect data | Cross-generator eval protocol reference |
| **Own generation** (SDXL/Flux "damaged product" images) | **BUILD** — domain-specific hard positives |

### Manipulation (L2 — eval only, TruFor is pretrained)
CASIA v1/v2 · COVERAGE · DEFACTO · IMD2020 · NIST MFC · Columbia splicing · CocoGlide

### Recapture (L3 — **BUILD, none exists at needed quality**)
- Screenshots of real + AI images (multiple OS/devices/scales)
- Phone-photo-of-screen (multiple screens × phones — moiré/glare variation)
- Print-then-photograph set
- Social-media roundtrip set (WhatsApp/Telegram/Instagram re-saves)

### E-commerce cross-check (L5 — **BUILD, the moat dataset**)
- Seller listing photos ↔ legit customer claim photos (same product)
- Synthetic fraud pairs: inpainted damage (SDXL inpainting) on listing-derived images
- Reused-damage-photo pairs (same damage photo across "different" claims)

## 9. Positioning statement

Incumbents sell **"is this media synthetic?"** We sell **"should you trust this return claim?"**
— a claims decision-support product with an audit trail, where synthetic-media detection is
one input of five. That's a different buyer (marketplace trust & safety / returns ops),
a different metric (fraud loss prevented, reviewer minutes saved), and a data moat
(listing↔claim pairs + reviewer feedback loop) that generic detectors can't reach.
