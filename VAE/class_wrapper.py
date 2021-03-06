"""
The class wrapper for the networks
"""
# Built-in
import os
import time

# Torch
import torch
from torch import nn
from torch.utils.tensorboard import SummaryWriter
# from torchsummary import summary
from torch.optim import lr_scheduler

# Libs
import numpy as np
from math import inf
# Own module

class Network(object):
    def __init__(self, model_fn, flags, train_loader, test_loader,
                 ckpt_dir=os.path.join(os.path.abspath(''), 'models'),
                 inference_mode=False, saved_model=None):
        self.model_fn = model_fn                                # The model maker function
        self.flags = flags                                      # The Flags containing the specs
        if inference_mode:                                      # If inference mode, use saved model
            self.ckpt_dir = os.path.join(ckpt_dir, saved_model)
            self.saved_model = saved_model
            print("This is inference mode, the ckpt is", self.ckpt_dir)
        else:                                                   # training mode, create a new ckpt folder
            if flags.model_name is None:
                self.ckpt_dir = os.path.join(ckpt_dir, time.strftime('%Y%m%d_%H%M%S', time.localtime()))
            else:
                self.ckpt_dir = os.path.join(ckpt_dir, flags.model_name)
        self.model = self.create_model()
        # self.encoder, self.decoder, self.spec_enc = self.create_model()     # The model itself
        # self.loss = self.make_loss()                            # The loss function
        self.optm = None                                        # The optimizer: Initialized at train() due to GPU
        self.optm_eval = None                                   # The eval_optimizer: Initialized at eva() due to GPU
        self.lr_scheduler = None                                # The lr scheduler: Initialized at train() due to GPU
        self.train_loader = train_loader                        # The train data loader
        self.test_loader = test_loader                          # The test data loader
        self.log = SummaryWriter(self.ckpt_dir)     # Create a summary writer for keeping the summary to the tensor board
        self.best_validation_loss = float('inf')    # Set the BVL to large number

    def create_model(self):
        """
        Function to create the network module from provided model fn and flags
        :return: the created nn module
        """
        # encoder = Encoder(self.flags)
        # decoder = Decoder(self.flags)
        # spec_enc = SpectraEncoder(self.flags)
        model = self.model_fn(self.flags)
        print(model)
        return model

    def make_loss(self, logit=None, labels=None, boundary=True, z_log_var=None, z_mean=None):
        """
        Create a tensor that represents the loss. This is consistant both at training time \
        and inference time for Backward model
        :param logit: The output of the network, the predicted geometry
        :param labels: The ground truth labels, the Truth geometry
        :param boundary: The boolean flag indicating adding boundary loss or not
        :param z_log_var: The log variance for VAE kl_loss
        :param z_mean: The z mean vector for VAE kl_loss
        :return: the total loss
        """
        # print("Size of logit", logit.size())
        # print("Size of labels", labels.size())
        mse_loss = nn.functional.mse_loss(logit, labels)          # The MSE Loss
        # BDY_loss
        if boundary:
            relu = torch.nn.ReLU()
            bdy_loss_all = relu(torch.abs(logit) - 1)
            bdy_loss = torch.mean(bdy_loss_all)
        kl_loss = 1 + z_log_var - torch.pow(z_mean, 2) - torch.exp(z_log_var)
        kl_loss = torch.mean(kl_loss)
        kl_loss *= -0.5
        total_loss = kl_loss + mse_loss + bdy_loss
        # print("size of kl_loss",kl_loss.size())
        # print("size of mse_loss",mse_loss.size())
        # print("size of bdy_loss",bdy_loss.size())
        return total_loss, [kl_loss.data.cpu().numpy(), mse_loss.data.cpu().numpy(), bdy_loss.data.cpu().numpy()]

    def make_optimizer(self):
        """
        Make the corresponding optimizer from the flags. Only below optimizers are allowed. Welcome to add more
        :return:
        """
        # parameters = [self.encoder.parameters(), self.decoder.parameters(), self.spec_enc.parameters()]
        if self.flags.optim == 'Adam':
            op = torch.optim.Adam(self.model.parameters(), lr=self.flags.lr, weight_decay=self.flags.reg_scale)
        elif self.flags.optim == 'RMSprop':
            op = torch.optim.RMSprop(self.model.parameters(), lr=self.flags.lr, weight_decay=self.flags.reg_scale)
        elif self.flags.optim == 'SGD':
            op = torch.optim.SGD(self.model.parameters(), lr=self.flags.lr, weight_decay=self.flags.reg_scale)
        else:
            raise Exception("Your Optimizer is neither Adam, RMSprop or SGD, please change in param or contact Ben")
        return op

    def make_lr_scheduler(self, optm):
        """
        Make the learning rate scheduler as instructed. More modes can be added to this, current supported ones:
        1. ReduceLROnPlateau (decrease lr when validation error stops improving
        :return:
        """
        return lr_scheduler.ReduceLROnPlateau(optimizer=optm, mode='min',
                                              factor=self.flags.lr_decay_rate,
                                              patience=10, verbose=True, threshold=1e-4)

    def save(self):
        """
        Saving the model to the current check point folder with name best_model_forward.pt
        :return: None
        """
        # torch.save(self.model.state_dict, os.path.join(self.ckpt_dir, 'best_model_state_dict.pt'))
        torch.save(self.model, os.path.join(self.ckpt_dir, 'best_model_forward.pt'))
        # torch.save(self.encoder, os.path.join(self.ckpt_dir, 'best_model_encoder.pt'))
        # torch.save(self.decoder, os.path.join(self.ckpt_dir, 'best_model_decoder.pt'))
        # torch.save(self.spec_enc, os.path.join(self.ckpt_dir, 'best_model_spec_enc.pt'))

    def load(self):
        """
        Loading the model from the check point folder with name best_model_forward.pt
        :return:
        """
        # self.model.load_state_dict(torch.load(os.path.join(self.ckpt_dir, 'best_model_state_dict.pt')))
        self.model = torch.load(os.path.join(self.ckpt_dir, 'best_model_forward.pt'))
        # self.encoder = torch.load(os.path.join(self.ckpt_dir, 'best_model_encoder.pt'))
        # self.decoder = torch.load(os.path.join(self.ckpt_dir, 'best_model_decoder.pt'))
        # self.spec_enc = torch.load(os.path.join(self.ckpt_dir, 'best_model_spec_enc.pt'))

    def train(self):
        """
        The major training function. This would start the training using information given in the flags
        :return: None
        """
        print("Starting training now")
        cuda = True if torch.cuda.is_available() else False
        if cuda:
            self.model.cuda()

        # Construct optimizer after the model moved to GPU
        self.optm = self.make_optimizer()
        self.lr_scheduler = self.make_lr_scheduler(self.optm)

        for epoch in range(self.flags.train_step):
            # Set to Training Mode
            train_loss = 0
            loss_aggregate_list = np.array([0., 0., 0.])       # kl_loss, mse_loss, bdy_loss
            self.model.train()
            for j, (geometry, spectra) in enumerate(self.train_loader):
                if cuda:
                    geometry = geometry.cuda()                          # Put data onto GPU
                    spectra = spectra.cuda()                            # Put data onto GPU
                self.optm.zero_grad()                               # Zero the gradient first
                G_pred, z_mean, z_log_var = self.model(geometry, spectra)              # Get G_pred
                # print("size of G_pred", G_pred.size())
                loss, loss_list = self.make_loss(logit=G_pred, labels=geometry, boundary=True,
                                                                   z_mean=z_mean, z_log_var=z_log_var)
                loss.backward()                                     # Calculate the backward gradients
                self.optm.step()                                    # Move one step the optimizer
                train_loss += loss                                  # Aggregate the loss
                loss_aggregate_list += loss_list                    # Aggregate the other loss (in np form)

            # Calculate the avg loss of training
            train_avg_loss = train_loss.cpu().data.numpy() / (j + 1)
            loss_aggregate_list /= (j+1)
            # boundary_avg_loss = boundary_loss.cpu().data.numpy() / (j + 1)

            if epoch % self.flags.eval_step == 0:                      # For eval steps, do the evaluations and tensor board
                # Record the training loss to the tensorboard
                self.log.add_scalar('Loss/total_train', train_avg_loss, epoch)
                self.log.add_scalar('Loss/kl_train', loss_aggregate_list[0], epoch)
                self.log.add_scalar('Loss/mse_train', loss_aggregate_list[1], epoch)
                self.log.add_scalar('Loss/bdy_train', loss_aggregate_list[2], epoch)

                # Set to Evaluation Mode
                self.model.eval()
                print("Doing Evaluation on the model now")
                test_loss = 0
                loss_aggregate_list = np.array([0., 0., 0.])  # kl_loss, mse_loss, bdy_loss
                for j, (geometry, spectra) in enumerate(self.test_loader):  # Loop through the eval set
                    if cuda:
                        geometry = geometry.cuda()
                        spectra = spectra.cuda()
                    G_pred, z_mean, z_log_var = self.model(geometry, spectra)  # Get G_pred
                    loss, loss_list = self.make_loss(logit=G_pred, labels=geometry, boundary=True,
                                          z_mean=z_mean, z_log_var=z_log_var)  # Get the loss tensor
                    test_loss += loss                                       # Aggregate the loss
                    loss_aggregate_list += loss_list                    # Aggregate the other loss (in np form)

                # Record the testing loss to the tensorboard
                test_avg_loss = test_loss.cpu().data.numpy() / (j+1)
                loss_aggregate_list /= (j + 1)
                self.log.add_scalar('Loss/total_test', test_avg_loss, epoch)
                self.log.add_scalar('Loss/kl_test', loss_aggregate_list[0], epoch)
                self.log.add_scalar('Loss/mse_test', loss_aggregate_list[1], epoch)
                self.log.add_scalar('Loss/bdy_test', loss_aggregate_list[2], epoch)

                print("This is Epoch %d, training loss %.5f, validation loss %.5f" \
                      % (epoch, train_avg_loss, test_avg_loss ))

                # Model improving, save the model down
                if test_avg_loss < self.best_validation_loss:
                    self.best_validation_loss = test_avg_loss
                    self.save()
                    print("Saving the model down...")

                    if self.best_validation_loss < self.flags.stop_threshold:
                        print("Training finished EARLIER at epoch %d, reaching loss of %.5f" %\
                              (epoch, self.best_validation_loss))
                        return None

            # Learning rate decay upon plateau
            self.lr_scheduler.step(train_avg_loss)

    def evaluate(self, save_dir='data/'):
        self.load()                             # load the model as constructed
        cuda = True if torch.cuda.is_available() else False
        if cuda:
            self.model.cuda()

        # Set to evaluation mode for batch_norm layers
        self.model.eval()
        self.model.bp = True

        # Construct optimizer after the model moved to GPU
        self.optm_eval = self.make_optimizer_eval()
        self.lr_scheduler = self.make_lr_scheduler(self.optm_eval)

        # Get the file names
        Ypred_file = os.path.join(save_dir, 'test_Ypred_{}.csv'.format(self.saved_model))
        Xtruth_file = os.path.join(save_dir, 'test_Xtruth_{}.csv'.format(self.saved_model))
        Ytruth_file = os.path.join(save_dir, 'test_Ytruth_{}.csv'.format(self.saved_model))
        Xpred_file = os.path.join(save_dir, 'test_Xpred_{}.csv'.format(self.saved_model))

        # Open those files to append
        with open(Xtruth_file, 'a') as fxt,open(Ytruth_file, 'a') as fyt,\
                open(Ypred_file, 'a') as fyp, open(Xpred_file, 'a') as fxp:
            # Loop through the eval data and evaluate
            for ind, (geometry, spectra) in enumerate(self.test_loader):
                if cuda:
                    geometry = geometry.cuda()
                    spectra = spectra.cuda()
                # Initialize the geometry first
                self.model.randomize_geometry_eval()
                self.optm_eval = self.make_optimizer_eval()
                self.lr_scheduler = self.make_lr_scheduler(self.optm_eval)
                Xpred, Ypred = self.evaluate_one(spectra)
                np.savetxt(fxt, geometry.cpu().data.numpy(), fmt='%.3f')
                np.savetxt(fyt, spectra.cpu().data.numpy(), fmt='%.3f')
                np.savetxt(fyp, Ypred, fmt='%.3f')
                np.savetxt(fxp, Xpred, fmt='%.3f')
        return Ypred_file, Ytruth_file

    def evaluate_one(self, target_spectra):
        # expand the target spectra to eval batch size
        target_spectra_expand = target_spectra.expand([self.flags.eval_batch_size, -1])
        # Start backprop
        for i in range(self.flags.eval_step):
            logit = self.model(self.model.geometry_eval)                      # Get the output
            loss = self.make_loss(logit, target_spectra_expand)         # Get the loss
            loss.backward()                           # Calculate the Gradient
            self.optm_eval.step()                                       # Move one step the optimizer

            # check periodically to stop and print stuff
            if i % self.flags.verb_step == 0:
                print("loss at inference step{} : {}".format(i, loss.data))     # Print loss
                if loss.data < self.flags.stop_threshold:                       # Check if stop
                    print("Loss is lower than threshold{}, inference stop".format(self.flags.stop_threshold))
                    break

        # Get the best performing one
        best_estimate_index = np.argmin(loss.cpu().data.numpy())
        Xpred_best = self.model.geometry_eval.cpu().data.numpy()[best_estimate_index, :]
        Ypred_best = logit.cpu().data.numpy()[best_estimate_index, :]

        return Xpred_best, Ypred_best

