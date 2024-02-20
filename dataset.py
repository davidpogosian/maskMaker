class Dataset:
    def __init__(self):
        self.data = []



# Not normalized.
class Datum:
    def __init__(self, imagePath, image, mask, herniated):
        self.imagePath = imagePath
        self.image = image
        self.mask = mask
        self.herniated = herniated