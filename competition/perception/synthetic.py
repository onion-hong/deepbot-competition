"""Deterministic diagnostic scenes, not a real-track benchmark."""
import argparse
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from .replay import write_json


SCENES = ('straight', 'left_curve', 'right_curve', 'shadow', 'no_line',
          'black_clutter', 'branch', 'roundabout', 'occlusion', 'blue_only',
          'no_blue_boundary', 'two_roads', 'discontinuous', 'narrow_dark_shadow')


def scene(name, width=320, height=240):
    image = Image.new('RGB', (width, height), (20, 75, 180))
    draw = ImageDraw.Draw(image)
    draw.rectangle((round(.12*width), 0, round(.88*width), height-1), fill=(235,235,235))
    points = []
    for y in range(height):
        shift = .15*width*((height-1-y)/(height-1))**2
        x = (width-1)/2 + (-shift if name == 'left_curve' else shift if name == 'right_curve' else 0)
        points.append((round(x), y))
    thickness = max(3, round(.025*width)) | 1
    if name not in ('no_line', 'blue_only', 'black_clutter', 'two_roads', 'narrow_dark_shadow'):
        draw.line(points, fill=(20,20,20), width=thickness)
    if name == 'shadow':
        arr = np.array(image)
        arr[round(.45*height):round(.8*height)] = (arr[round(.45*height):round(.8*height)]*.62).astype(np.uint8)
        image = Image.fromarray(arr)
    if name == 'black_clutter':
        draw.rectangle((.35*width, .48*height, .67*width, .8*height), fill='black')
    if name == 'branch':
        draw.line([(.5*width,.75*height),(.27*width,.4*height)], fill='black', width=thickness)
        draw.line([(.5*width,.75*height),(.73*width,.4*height)], fill='black', width=thickness)
    if name == 'roundabout':
        draw.ellipse((.3*width,.4*height,.7*width,.8*height), outline='black', width=thickness)
    if name == 'occlusion':
        draw.rectangle((.28*width,.55*height,.72*width,.72*height), fill=(20,75,180))
    if name == 'blue_only':
        draw.rectangle((0,0,width,height), fill=(20,75,180))
    if name == 'no_blue_boundary':
        draw.rectangle((0,0,.12*width,height), fill='white')
        draw.rectangle((.88*width,0,width,height), fill='white')
    if name == 'two_roads':
        draw.rectangle((.46*width,0,.54*width,height), fill=(20,75,180))
        for x in (.3,.7):
            draw.line([(x*width,0),(x*width,height)], fill='black', width=thickness)
    if name == 'discontinuous':
        draw.rectangle((.4*width,.55*height,.6*width,.75*height), fill=(235,235,235))
    if name == 'narrow_dark_shadow':
        # Deliberately indistinguishable from a thin painted line in RGB. This
        # exposes a known pixel-estimator false positive, not a semantic claim.
        draw.line(points, fill=(55,55,55), width=thickness)
    return np.array(image)


def generate(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for name in SCENES:
        with (output / (name + '.png')).open('xb') as stream:
            Image.fromarray(scene(name)).save(stream, format='PNG')
    write_json(output / 'SCENES.json', dict(role='synthetic', scenes=SCENES,
               limitation='Hand-designed cases used during implementation, not held-out validation.'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    generate(parser.parse_args().output)
