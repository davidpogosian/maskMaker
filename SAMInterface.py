import sys
import numpy as np
from segment_anything import sam_model_registry, SamPredictor

sam_checkpoint = "sam_vit_h_4b8939.pth"
model_type = "vit_h"
device = "cpu"

class SAMInterface:
    def __init__(self):
        sam = sam_model_registry[model_type](checkpoint=sam_checkpoint)
        sam.to(device=device)
        self.predictor = SamPredictor(sam)
        self.inputBox = None
        self.image = None

    def setImage(self, image):
        self.image = image
        self.predictor.set_image(image)

    def setBox(self, box):
        self.inputBox = np.array(box)

    def predict(self):
        mask, _, _ = self.predictor.predict(
            point_coords=None,
            point_labels=None,
            box=self.inputBox[None, :],
            multimask_output=False,
        )
        return mask


















