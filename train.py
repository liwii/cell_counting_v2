# -*- coding: utf-8 -*-
"""
Created on Fri Jan 27 19:12:53 2017

@author: Weidi Xie

@Description: This is the file used for training, loading images, annotation, training with model.
"""

import numpy as np
import pdb
import os
import sys
import matplotlib.pyplot as plt
from generator import ImageDataGenerator
from model import buildModel_FCRN_A_v2_2channel, buildModel_U_net_2channel
from tensorflow.keras import backend as K
from keras.callbacks import ModelCheckpoint,Callback,LearningRateScheduler
from imageio import imread
import scipy.ndimage as ndimage
import cv2

class LossHistory(Callback):
    def on_train_begin(self, logs={}):
        self.losses = []

    def on_batch_end(self, batch, logs={}):
        self.losses.append(logs.get('loss'))

#base_path = 'cells/'
base_path = 'data/'
out_path = 'out/'
data = []
anno_viable = []
anno_dead = []

def step_decay(epoch):
    step = 16
    num =  epoch // step 
    if num % 3 == 0:
        lrate = 1e-3
    elif num % 3 == 1:
        lrate = 1e-4
    else:
        lrate = 1e-5
        #lrate = initial_lrate * 1/(1 + decay * (epoch - num * step))
    print('Learning rate for epoch {} is {}.'.format(epoch+1, lrate))
    return np.float(lrate)
    
#def read_data(base_path):
#    imList = os.listdir(base_path)
#    for i in range(len(imList)):
#        if 'cell' in imList[i]:
#            img1 = imread(os.path.join(base_path,imList[i]))
#            data.append(img1)
#
#            img2_ = imread(os.path.join(base_path, imList[i][:3] + 'dots.png'))
#            img2 = 100.0 * (img2_[:,:,0] > 0)
#            img2 = ndimage.gaussian_filter(img2, sigma=(1, 1), order=0)
#            anno.append(img2)
#            breakpoint()
#    return np.asarray(data, dtype = 'float32'), np.asarray(anno, dtype = 'float32')

def process_annodata(pathname):
    img_ = np.rot90(imread(pathname), -1)
    img = np.zeros((int(img_.shape[0] / 8), int(img_.shape[1] / 8)))
    for i in range(0, img_.shape[0], 8):
        for j in range(0, img_.shape[1], 8):
            img[i // 8][j // 8] = img_[i:i+8, j:j+8].max()
    img = 100.0 * (img > 0)
    img = ndimage.gaussian_filter(img, sigma=(2, 2), order=0)
    return img[0:504, 0:376]


def read_data(base_path):
    imList = os.listdir(base_path)
    for i in range(len(imList)):
        im = imList[i]
        print(i)
        print(im)
        img1 = imread(os.path.join(base_path,im))
        img1 = cv2.resize(img1, None, fx=0.125, fy=0.125)
        img1 = img1[0:504, 0:376]
        data.append(img1)
        imname, _ = os.path.splitext(im)
        img_viable = process_annodata(os.path.join(out_path, "{}_viable.png".format(imname)))
        anno_viable.append(img_viable)
        img_dead = process_annodata(os.path.join(out_path, "{}_dead.png".format(imname)))
        anno_dead.append(img_dead)
    print("finish!!")
    return np.asarray(data, dtype = 'float32'), np.asarray(anno_viable, dtype = 'float32') , np.asarray(anno_dead, dtype = 'float32')

def learn(filename, train_data, train_anno, val_data, val_anno, model):
    print(filename)
    model_checkpoint = ModelCheckpoint(filename, monitor='loss', save_best_only=True)
    model.summary()
    print('...Fitting model...')
    print('-'*30)
    change_lr = LearningRateScheduler(step_decay)

    datagen = ImageDataGenerator(
        featurewise_center = False,  # set input mean to 0 over the dataset
        samplewise_center = False,  # set each sample mean to 0
        featurewise_std_normalization = False,  # divide inputs by std of the dataset
        samplewise_std_normalization = False,  # divide each input by its std
        zca_whitening = False,  # apply ZCA whitening
        rotation_range = 30,  # randomly rotate images in the range (degrees, 0 to 180)
        width_shift_range = 0.3,  # randomly shift images horizontally (fraction of total width)
        height_shift_range = 0.3,  # randomly shift images vertically (fraction of total height)
        zoom_range = 0.3,
        shear_range = 0.,
        horizontal_flip = True,  # randomly flip images
        vertical_flip = True, # randomly flip images
        fill_mode = 'constant',
        dim_ordering = 'tf')  

    # Fit the model on the batches generated by datagen.flow().
    batch_size = 8
    model.fit_generator(datagen.flow(train_data,
                                     train_anno,
                                     batch_size = batch_size
                                     ),
                        steps_per_epoch = train_data.shape[0] // batch_size,
                        epochs = 192,
                        callbacks = [model_checkpoint, change_lr],
                       )
    
    model.load_weights(filename)
    A = model.predict(val_data)
    mean_diff = np.average(np.abs(np.sum(np.sum(A,1),1)-np.sum(np.sum(val_anno,1),1))) / (100.0)
    print('After training, the difference is : {} cells per image.'.format(np.abs(mean_diff)))
    
def train_(base_path):
    data, anno_viable, anno_dead = read_data(base_path)
    print("loaded!!")
    anno = np.stack([anno_viable, anno_dead], axis = 3)
    print("expanded!!")
    
    mean = np.mean(data)
    print("mean finished!!")
    std = np.std(data)
    print("std finished!!")
    
    data_ = (data - mean) / std
    
    train_data = data_[:50]
    train_anno = anno[:50]

    val_data = data_[50:]
    val_anno = anno[50:]

    print('-'*30)
    print('Creating and compiling the fully convolutional regression networks.')
    print('-'*30)    
   
    if sys.argv[1] == 'unet':
        model = buildModel_U_net_2channel(input_dim = (504, 376,3))
        filename = 'cell_counting_2channel_unet_pzone.hdf5'
    elif sys.argv[1] == 'fcrna':
        model = buildModel_FCRN_A_v2_2channel(input_dim = (504, 376,3))
        filename = 'cell_counting_2channel_fcrna_pzone.hdf5'
    else:
        raise ValueError('The first command line argument should be "unet" or "fcrna"')
    learn(filename, train_data, train_anno, val_data, val_anno, model)
    
if __name__ == '__main__':
    train_(base_path)
