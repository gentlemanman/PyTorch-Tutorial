import torch
from torch import nn
from torchvision import transforms
from torch.utils.data import DataLoader, sampler
from torchvision.datasets import MNIST

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec


NUM_TRAIN = 50000
NUM_VAL = 5000
NOISE_DIM = 96
batch_size = 128

def show_images(images):
    images =np.reshape(images, [images.shape[0], -1])
    sqrtn = int(np.ceil(np.sqrt(images.shape[0])))
    sqrtimg = int(np.ceil(np.sqrt(images.shape[1])))
    fig = plt.figure(figsize=(sqrtn, sqrtn))
    gs = gridspec.GridSpec(sqrtn, sqrtn)
    gs.update(wspace=0.05, hspace=0.05)

    for i, img in enumerate(images):
        ax = plt.subplot(gs[i])
        plt.axis('off')
        ax.set_xticklabels([])
        ax.set_yticklabels([])
        ax.set_aspect('equal')
        plt.imshow(img.reshape([sqrtimg, sqrtimg]))
        # plt.show()
    return

def preprocess_img(x):
    x = transforms.ToTensor()(x)
    return (x - 0.5) / 0.5
def deprocess_img(x):
    return (x + 1.0) / 2.0

class ChunkSampler(sampler.Sampler):
    def __init__(self, num_samples, start=0):
        self.num_samples = num_samples
        self.start = start
    def __iter__(self):
        return iter(range(self.start, self.start + self.num_samples))
    def __len__(self):
        return self.num_samples


train_set = MNIST('./mnist', train=True, download=True, transform=preprocess_img)
train_data = DataLoader(train_set, batch_size=batch_size, sampler=ChunkSampler(NUM_TRAIN, 0))
val_set = MNIST('./mnist', download=True, transform=preprocess_img)
val_data = DataLoader(val_set, batch_size=batch_size, sampler=ChunkSampler(NUM_VAL, NUM_TRAIN))


class build_dc_classifier(nn.Module):
    def __init__(self):
        super (build_dc_classifier, self).__init__()
        self.conv = nn.Sequential(
            nn.Conv2d(1, 32, 5, 1),
            nn.LeakyReLU(0.01),
            nn.MaxPool2d(2, 2),
            nn.Conv2d(32, 64, 5, 1),
            nn.LeakyReLU(0.01),
            nn.MaxPool2d(2, 2) # b, 64, 4, 4
        )
        self.fc = nn.Sequential(
            nn.Linear(1024, 1024),
            nn.LeakyReLU(0.01),
            nn.Linear(1024, 1)
        )
    def forward(self, x):
        x = self.conv(x)
        x = x.view(x.shape[0], -1)
        x = self.fc(x)
        return x

class build_dc_generator(nn.Module):
    def __init__(self, noise_dim=NOISE_DIM):
        super(build_dc_generator, self).__init__()
        self.fc = nn.Sequential(
            nn.Linear(noise_dim, 1024),
            nn.ReLU(True),
            nn.BatchNorm1d(1024),
            nn.Linear(1024, 7*7*128),
            nn.ReLU(True),
            nn.BatchNorm1d(7*7*128),
        )
        self.conv = nn.Sequential(
            nn.ConvTranspose2d(128, 64, 4, 2, padding=1),
            nn.ReLU(True),
            nn.BatchNorm2d(64),
            nn.ConvTranspose2d(64, 1, 4, 2, padding=1),
            nn.Tanh()
        )
    def forward(self, x):
        x = self.fc(x)
        x = x.view(x.shape[0], 128, 7, 7)
        x = self.conv(x)
        return x

bce_loss = nn.BCEWithLogitsLoss()
def D_loss(logits_real, logits_fake):
    size = logits_real.shape[0]
    true_labels = torch.ones(size, 1).float().cuda()
    false_labels = torch.zeros(size, 1).float().cuda()
    loss = bce_loss(logits_real, true_labels) + bce_loss(logits_fake, false_labels)
    return loss

def G_loss(logits_fake):
    size = logits_fake.shape[0]
    true_labels = torch.ones(size, 1).float().cuda()
    loss = bce_loss(logits_fake, true_labels)
    return loss

def get_opimizer(net):
    optimizer = torch.optim.Adam(net.parameters(), lr=3e-4, betas=(0.5, 0.999))
    return optimizer

def train_dc_gan(D_net, G_net, D_optimizer, G_optimizer, D_loss, G_loss, show_every=250,
                     noise_size=96, num_epochs=10):
    iter_count = 0
    for epoch in range(num_epochs):
        for x, _ in train_data:
            bs = x.shape[0]
            # 判别网络
            real_data = x.cuda()

            logits_real = D_net(real_data) # 判别器得分

            sample_noise = (torch.rand(bs, noise_size) - 0.5) / 0.5
            g_fake_seed = sample_noise.cuda()
            fake_images = G_net(g_fake_seed) # 生成假的数据
            logits_fake = D_net(fake_images)
            d_total_error = D_loss(logits_real, logits_fake) #判别器的loss

            D_optimizer.zero_grad()
            d_total_error.backward()
            D_optimizer.step()# 优化判别网络

            # 生成网络
            g_fake_seed = sample_noise.cuda()
            fake_images = G_net(g_fake_seed)# 生成假的数据
            gen_logits_fake = D_net(fake_images)
            g_error = G_loss(gen_logits_fake)
            G_optimizer.zero_grad()
            g_error.backward()
            G_optimizer.step() # 优化生成网络

            if iter_count % show_every == 0:
                print('Iter:{}, D:{:.4}, G:{:.4}'.format(iter_count, d_total_error.item(), g_error.item()))
                imgs_numpy = deprocess_img(fake_images.data.cpu().numpy())
                show_images(imgs_numpy[0:16])
            iter_count += 1

D_DC = build_dc_classifier().cuda()
G_DC = build_dc_generator().cuda()

D_DC_optim = get_opimizer(D_DC)
G_DC_optim = get_opimizer(G_DC)

train_dc_gan(D_DC, G_DC, D_DC_optim, G_DC_optim, D_loss, G_loss, num_epochs=10)





















