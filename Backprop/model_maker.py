"""
This is the module where the model is defined. It uses the nn.Module as backbone to create the network structure
"""
# Own modules

# Built in
import math
# Libs
import numpy as np

# Pytorch module
import torch.nn as nn
import torch.nn.functional as F
import torch
from torch import pow, add, mul, div, sqrt


class Backprop(nn.Module):
    def __init__(self, flags):
        super(Backprop, self).__init__()
        self.bp = False                                                 # The flag that the model is backpropagating
        # Initialize the geometry_eval field
        self.geometry_eval = torch.randn([flags.eval_batch_size, flags.linear[0]], requires_grad=True)
        # Linear Layer and Batch_norm Layer definitions here
        self.linears = nn.ModuleList([])
        self.bn_linears = nn.ModuleList([])
        for ind, fc_num in enumerate(flags.linear[0:-1]):               # Excluding the last one as we need intervals
            self.linears.append(nn.Linear(fc_num, flags.linear[ind + 1]))
            self.bn_linears.append(nn.BatchNorm1d(flags.linear[ind + 1]))

        # Conv Layer definitions here
        self.convs = nn.ModuleList([])
        in_channel = 1                                                  # Initialize the in_channel number
        for ind, (out_channel, kernel_size, stride) in enumerate(zip(flags.conv_out_channel,
                                                                     flags.conv_kernel_size,
                                                                     flags.conv_stride)):
            if stride == 2:     # We want to double the number
                pad = int(kernel_size/2 - 1)
            elif stride == 1:   # We want to keep the number unchanged
                pad = int((kernel_size - 1)/2)
            else:
                Exception("Now only support stride = 1 or 2, contact Ben")

            self.convs.append(nn.ConvTranspose1d(in_channel, out_channel, kernel_size,
                                stride=stride, padding=pad)) # To make sure L_out double each time
            in_channel = out_channel # Update the out_channel
        if len(self.convs):                     # Make sure there is not en empty one
            self.convs.append(nn.Conv1d(in_channel, out_channels=1, kernel_size=1, stride=1, padding=0))

    def init_geometry_eval(self, flags):
        """
        The initialization function during inference time
        :param flags: The flag carrying new informaiton about evaluation time
        :return: Randomly initialized geometry
        """
        # Initialize the geometry_eval field
        print("Eval Geometry Re-initialized")
        self.geometry_eval = torch.randn([flags.eval_batch_size, flags.linear[0]], requires_grad=True)

    def randomize_geometry_eval(self):
        self.geometry_eval = torch.randn_like(self.geometry_eval, requires_grad=True)       # Randomize

    def forward(self, G):
        """
        The forward function which defines how the network is connected
        :param G: The input geometry (Since this is a forward network)
        :return: S: The 300 dimension spectra
        """
        out = G                                                         # initialize the out
        if self.bp:                                               # If the evaluation mode
            out = self.geometry_eval
        # For the linear part
        for ind, (fc, bn) in enumerate(zip(self.linears, self.bn_linears)):
            out = F.relu(bn(fc(out)))                                   # ReLU + BN + Linear

        # The normal mode to train without Lorentz
        out = out.unsqueeze(1)                                          # Add 1 dimension to get N,L_in, H
        # For the conv part
        for ind, conv in enumerate(self.convs):
            #print(out.size())
            out = conv(out)
        S = out.squeeze()
        return S

