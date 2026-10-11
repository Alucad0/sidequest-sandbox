import io

try:
    from PIL import Image
except ImportError:
    Image = None

BACKGROUND = (245, 222, 120)
SILHOUETTE = (25, 25, 40)


def can_render() -> bool:
    return Image is not None


def render(png: bytes, silhouette: bool) -> str:
    # draws the sprite in the terminal, two pixels per character using the upper half block
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    box = image.getchannel("A").getbbox()
    if box:
        image = image.crop(box)
    width, height = image.size
    pixels = image.load()

    def colour(x, y):
        if y >= height:
            return BACKGROUND
        r, g, b, a = pixels[x, y]
        if a < 128:
            return BACKGROUND
        return SILHOUETTE if silhouette else (r, g, b)

    lines = []
    for y in range(-2, height + 2, 2):
        line = ""
        for x in range(-2, width + 2):
            top = colour(x, y) if 0 <= x < width and y >= 0 else BACKGROUND
            bottom = colour(x, y + 1) if 0 <= x < width and y + 1 >= 0 else BACKGROUND
            line += f"\033[38;2;{top[0]};{top[1]};{top[2]}m\033[48;2;{bottom[0]};{bottom[1]};{bottom[2]}m▀"
        lines.append(line + "\033[0m")
    return "\n".join(lines)
