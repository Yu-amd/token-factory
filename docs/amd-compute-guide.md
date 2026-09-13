# AMD Compute Guide

Token Factory routes to AIM-backed models on three accelerator families:

## Instinct (MI250X–MI355X)

Primary datacenter GPUs. GPT-OSS 120B/20B are **optimized** on MI300X/MI350X/MI355X per [AMD AIM matrix](https://enterprise-ai.docs.amd.com/en/latest/aims/accelerator_support.html).

## EPYC (9965, ZEN4, ZEN5)

CPU inference for smaller models. Support levels are often `preview` or `general`.

## Radeon (R9700, W7900)

Edge/client GPUs. ROCm **7.13+** required for Radeon AIMs.

## Using the catalog

`catalog/aims.yaml` mirrors public AIM support levels. The compiler and CLI use it for eligibility checks and UI inventory.

```bash
make update-aim-catalog   # refresh from scripts/generate-aim-catalog.py
token-factory route-explain "Write a Python sort function"
```
