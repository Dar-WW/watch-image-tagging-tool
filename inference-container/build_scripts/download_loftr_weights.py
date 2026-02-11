"""Pre-download LoFTR weights during Docker build.

This script ensures the LoFTR 'outdoor' pretrained weights are cached
locally so they don't need to be downloaded at runtime (cold start).
"""

import torch
from kornia.feature import LoFTR


def main():
    print("Pre-downloading LoFTR 'outdoor' weights...")
    model = LoFTR(pretrained="outdoor")
    print(f"LoFTR model loaded successfully ({sum(p.numel() for p in model.parameters())} parameters)")

    # Verify it works with a dummy forward pass
    dummy_input = {
        "image0": torch.randn(1, 1, 64, 64),
        "image1": torch.randn(1, 1, 64, 64),
    }
    with torch.no_grad():
        output = model(dummy_input)
    print(f"Dummy inference OK: {len(output['keypoints0'])} matches")
    print("LoFTR weights cached successfully")


if __name__ == "__main__":
    main()
