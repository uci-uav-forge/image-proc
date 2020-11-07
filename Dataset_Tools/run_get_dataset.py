import argparse
import subprocess
import string
import sys
sys.path.append('')


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--num_images", type=int, required=True, help='number of images per shape letter pair')
    parser.add_argument("--blender_path", type=str, required=True, help='path to blender on your device')
    args = parser.parse_args()

    shapes_list = ['Half_Circle', 'Circle', 'Heart', 'Plus', 'Square', 'Triangle']
    letters_list = list(string.ascii_uppercase)

    for shape in shapes_list:
        for letter in letters_list:
            command = "{} --background --use-extension 1 -E CYCLES -t 0 -P 'get_dataset.py' -- --shape {} --letter {} --num_images {}".format(args.blender_path, shape, letter, args.num_images)
            process = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, universal_newlines=True)
            output = process.stdout
            print(output)