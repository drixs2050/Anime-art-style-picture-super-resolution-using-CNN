import argparse

import torch
import torch.backends.cudnn as cudnn
import numpy as np
import PIL.Image as pil_image
from datetime import datetime
from models import ACNet
from utils import convert_ycbcr_to_rgb, preprocess, calc_psnr, compress_img


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--weights-file', type=str, required=True)
    parser.add_argument('--image-file', type=str, required=True)
    parser.add_argument('--scale', type=int, default=2)
    parser.add_argument('--compress', action='store_true')
    parser.add_argument('--quality', type=int, default=60)
    parser.add_argument('--crop', action='store_true')
    parser.add_argument('--top', type=int, default=760)
    parser.add_argument('--left', type=int, default=160)
    parser.add_argument('--side_len', type=int, default=100)
    args = parser.parse_args()

    cudnn.benchmark = True
    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')

    model = ACNet(scale_factor=args.scale).to(device)

    state_dict = model.state_dict()
    for n, p in torch.load(args.weights_file, map_location=lambda storage, loc: storage).items():
        if n in state_dict.keys():
            state_dict[n].copy_(p)
        else:
            raise KeyError(n)

    model.eval()

    image = pil_image.open(args.image_file).convert('RGB')

    image_width = (image.width // args.scale) * args.scale
    image_height = (image.height // args.scale) * args.scale

    hr = image.resize((image_width, image_height), resample=pil_image.BICUBIC)
    if args.crop:
        hr.crop((args.left, args.top, args.left+args.side_len, args.top+args.side_len)). \
            save(args.image_file.replace('.', '_origin_thumbnail_{}.'.format(args.scale, args.quality)))
    lr = hr.resize((hr.width // args.scale, hr.height // args.scale), resample=pil_image.BICUBIC)
    if args.compress:
        lr = compress_img(lr, args.quality)
    lr.save(args.image_file.replace('.png', '_source_{}.jpg').format(args.quality), format='jpeg', quality=100, subsampling=0)
    if args.crop:
        lr.crop((args.left//args.scale, args.top//args.scale, args.left+args.side_len//args.scale, args.top+args.side_len//args.scale)).\
            save(args.image_file.replace('.png', '_source_thumbnail_{}.jpg').format(args.quality), format='jpeg', quality=100, subsampling=0)
    start = datetime.now()
    bicubic = lr.resize((lr.width * args.scale, lr.height * args.scale), resample=pil_image.BICUBIC)
    end = datetime.now()
    time_taken = end - start
    print('Bicubic_Time: ', time_taken)
    bicubic.save(args.image_file.replace('.', '_bicubic_x{}_{}.'.format(args.scale, args.quality)))
    if args.crop:
        bicubic.crop((args.left, args.top, args.left+args.side_len, args.top+args.side_len)).\
            save(args.image_file.replace('.', '_bicubic_x{}_thumbnail_{}.'.format(args.scale, args.quality)))

    lr, _ = preprocess(lr, device)
    hr, _ = preprocess(hr, device)
    bicubic, ycbcr = preprocess(bicubic, device)
    psnr = calc_psnr(hr, bicubic)
    print('PSNR_bicubic: {:.2f}'.format(psnr))

    with torch.no_grad():
        start = datetime.now()
        preds = model(lr).clamp(0.0, 1.0)
        end = datetime.now()
        time_taken = end - start
        print('Time: ', time_taken)
    psnr = calc_psnr(hr, preds)
    print('PSNR: {:.2f}'.format(psnr))

    preds = preds.mul(255.0).cpu().numpy().squeeze(0).squeeze(0)

    output = np.array([preds, ycbcr[..., 1], ycbcr[..., 2]]).transpose([1, 2, 0])
    output = np.clip(convert_ycbcr_to_rgb(output), 0.0, 255.0).astype(np.uint8)
    output = pil_image.fromarray(output)
    output.save(args.image_file.replace('.', '_ACNet_x{}_{}.'.format(args.scale, args.quality)))
    if args.crop:
        output.crop((args.left, args.top, args.left+args.side_len, args.top+args.side_len)).\
            save(args.image_file.replace('.', '_ACNet_x{}_thumbnail_{}.'.format(args.scale, args.quality)))
