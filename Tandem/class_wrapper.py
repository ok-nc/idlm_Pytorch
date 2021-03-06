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
    def __init__(self, model_fn_f, model_fn_b, flags, train_loader, test_loader,
                 ckpt_dir=os.path.join(os.path.abspath(''), 'models'),
                 inference_mode=False, saved_model=None):
        """
        The initializer of the Network class which is the wrapper of our neural network, this is for the Tandem model
        :param model_fn_f:
        :param model_fn_b:
        :param flags:
        :param train_loader:
        :param test_loader:
        :param ckpt_dir:
        :param inference_mode:
        :param saved_model:
        """
        self.model_fn_f = model_fn_f                                # The model maker function for forward
        self.model_fn_b = model_fn_b                                # The model maker function for backward
        self.load_forward_ckpt_dir = flags.load_forward_ckpt_dir    # The pre-trained forward model ckpt dir
        print("The pretrian model to load is:", self.load_forward_ckpt_dir)
        self.flags = flags                                      # The Flags containing the specs
        if inference_mode:                                      # If inference mode, use saved model
            self.ckpt_dir = os.path.join(ckpt_dir, saved_model)
            self.saved_model = saved_model
            print("This is inference mode, the ckpt is", self.ckpt_dir)
        else:                                                   # training mode, create a new ckpt folder
            if flags.model_name is None:                    # leave custume name if possible
                self.ckpt_dir = os.path.join(ckpt_dir, time.strftime('%Y%m%d_%H%M%S', time.localtime()))
            else:
                self.ckpt_dir = os.path.join(ckpt_dir, flags.model_name)
        self.model_f, self.model_b = self.create_model()                        # The model itself
        self.loss = self.make_loss()                            # The loss function
        self.optm_f = None                                      # The optimizer: Initialized at train() due to GPU
        self.optm_b = None                                      # The eval_optimizer: Initialized at eva() due to GPU
        self.lr_scheduler = None                                # The lr scheduler: Initialized at train() due to GPU
        self.train_loader = train_loader                        # The train data loader
        self.test_loader = test_loader                          # The test data loader
        self.log = SummaryWriter(self.ckpt_dir)                 # Create a summary writer for keeping the summary to the tensor board
        self.best_validation_loss = float('inf')                # Set the BVL to large number

    def make_optimizer_b(self):
        """
        The function to make the optimizer during evaluation time.
        The difference between optm is that it does not have regularization and it only optmize the self.geometr_eval tensor
        :return: the optimizer_eval
        """
        if self.flags.optim == 'Adam':
            op = torch.optim.Adam(self.model_b.parameters(), lr=self.flags.lr)
        elif self.flags.optim == 'RMSprop':
            op = torch.optim.RMSprop(self.model_b.parameters(), lr=self.flags.lr)
        elif self.flags.optim == 'SGD':
            op = torch.optim.SGD(self.model_b.parameters(), lr=self.flags.lr)
        else:
            raise Exception("Your Optimizer is neither Adam, RMSprop or SGD, please change in param or contact Ben")
        return op

    def create_model(self):
        """
        Function to create the network module from provided model fn and flags
        :return: the created nn module
        """
        model_f = self.model_fn_f(self.flags)
        model_b = self.model_fn_b(self.flags)
        print("Forward model", model_f)
        print("Backward model", model_b)
        return model_f, model_b

    def make_loss(self, logit=None, labels=None, G=None):
        """
        Create a tensor that represents the loss. This is consistant both at training time \
        and inference time for Backward model
        :param logit: The output of the network
        :param labels: The ground truth labels
        :param G: The geometry predicted
        :return: the total loss
        """
        if logit is None:
            return None
        BDY_loss = torch.zeros(size=[])
        self.Boundary_loss = BDY_loss
        if self.flags.data_set != 'gaussian_mixture':
            MSE_loss = nn.functional.mse_loss(logit, labels)          # The MSE Loss

            # Boundary loss of the geometry_eval to be less than 1
            if G is not None:
                relu = torch.nn.ReLU()
                BDY_loss_all = relu(torch.abs(G) - 1)
                BDY_loss = torch.mean(BDY_loss_all)
            self.MSE_loss = MSE_loss
            self.Boundary_loss = BDY_loss
            return torch.add(MSE_loss, BDY_loss)
        else:  # This is cross entropy loss where data is categorical
            criterion = nn.CrossEntropyLoss()
            return criterion(logit, labels.long())

    def make_optimizer_f(self):
        """
        Make the corresponding optimizer from the flags. Only below optimizers are allowed. Welcome to add more
        :return:
        """
        if self.flags.optim == 'Adam':
            op = torch.optim.Adam(self.model_f.parameters(), lr=self.flags.lr, weight_decay=self.flags.reg_scale)
        elif self.flags.optim == 'RMSprop':
            op = torch.optim.RMSprop(self.model_f.parameters(), lr=self.flags.lr, weight_decay=self.flags.reg_scale)
        elif self.flags.optim == 'SGD':
            op = torch.optim.SGD(self.model_f.parameters(), lr=self.flags.lr, weight_decay=self.flags.reg_scale)
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

    def save_f(self):
        """
        Saving the model to the current check point folder with name best_model_forward.pt
        :return: None
        """
        # torch.save(self.model.state_dict, os.path.join(self.ckpt_dir, 'best_model_state_dict.pt'))
        torch.save(self.model_f, os.path.join(self.ckpt_dir, 'best_model_forward.pt'))

    def save_b(self):
        """
        Saving the model to the current check point folder with name best_model_forward.pt
        :return: None
        """
        torch.save(self.model_b, os.path.join(self.ckpt_dir, 'best_model_backward.pt'))

    def load_f(self):
        """
        Only loading the forward model to using the check point folder with name best_model_forward.pt
        :return: None
        """
        self.model_f = torch.load(os.path.join(self.load_forward_ckpt_dir, 'best_model_forward.pt'))

    def load(self):
        """
        Loading the model from the check point folder with name best_model_forward.pt
        :return:
        """
        # self.model.load_state_dict(torch.load(os.path.join(self.ckpt_dir, 'best_model_state_dict.pt')))
        self.model_f = torch.load(os.path.join(self.ckpt_dir, 'best_model_forward.pt'))
        self.model_b = torch.load(os.path.join(self.ckpt_dir, 'best_model_backward.pt'))

    def train(self):
        """
        The major training function. This would start the training using information given in the flags
        :return: None
        """
        """
        Forward Training part
        """
        cuda = True if torch.cuda.is_available() else False
        if cuda:
            self.model_f.cuda()
            self.model_b.cuda()
        if self.load_forward_ckpt_dir is None:
            print("Start Forward Training now")
            # Construct optimizer after the model moved to GPU
            self.optm_f = self.make_optimizer_f()
            self.lr_scheduler = self.make_lr_scheduler(self.optm_f)

            for epoch in range(self.flags.train_step):
                # Set to Training Mode
                train_loss = 0
                # boundary_loss = 0                 # Unnecessary during training since we provide geometries
                self.model_f.train()
                for j, (geometry, spectra) in enumerate(self.train_loader):
                    if cuda:
                        geometry = geometry.cuda()                          # Put data onto GPU
                        spectra = spectra.cuda()                            # Put data onto GPU
                    self.optm_f.zero_grad()                                   # Zero the gradient first
                    S_out = self.model_f(geometry)     # Get the output
                    loss = self.make_loss(S_out, spectra)                   # Get the loss tensor
                    loss.backward()                                         # Calculate the backward gradients
                    self.optm_f.step()                                      # Move one step the optimizer
                    train_loss += loss                                      # Aggregate the loss
                    # boundary_loss += self.Boundary_loss                   # Aggregate the BDY loss

                # Calculate the avg loss of training
                train_avg_loss = train_loss.cpu().data.numpy() / (j + 1)
                # boundary_avg_loss = boundary_loss.cpu().data.numpy() / (j + 1)

                if epoch % self.flags.eval_step == 0:                      # For eval steps, do the evaluations and tensor board
                    # Record the training loss to the tensorboard
                    self.log.add_scalar('Loss/forward_train', train_avg_loss, epoch)
                    # self.log.add_scalar('Loss/BDY_train', boundary_avg_loss, epoch)

                    # Set to Evaluation Mode
                    self.model_f.eval()
                    print("Doing Evaluation on the forward model now")
                    test_loss = 0
                    for j, (geometry, spectra) in enumerate(self.test_loader):  # Loop through the eval set
                        if cuda:
                            geometry = geometry.cuda()
                            spectra = spectra.cuda()
                        logit = self.model_f(geometry)
                        loss = self.make_loss(logit, spectra)                   # compute the loss
                        test_loss += loss                                       # Aggregate the loss

                    # Record the testing loss to the tensorboard
                    test_avg_loss = test_loss.cpu().data.numpy() / (j+1)
                    self.log.add_scalar('Loss/forward_test', test_avg_loss, epoch)

                    print("This is Epoch %d, training loss %.5f, validation loss %.5f" \
                          % (epoch, train_avg_loss, test_avg_loss ))

                    # Model improving, save the model down
                    if test_avg_loss < self.best_validation_loss:
                        self.best_validation_loss = test_avg_loss
                        self.save_f()
                        print("Saving the model down...")

                        if self.best_validation_loss < self.flags.stop_threshold:
                            print("Training finished EARLIER at epoch %d, reaching loss of %.5f" %\
                                  (epoch, self.best_validation_loss))
                            return None

                # Learning rate decay upon plateau
                self.lr_scheduler.step(train_avg_loss)
        else:
            print("Loading the pre-trained forward model instead of training it")
            self.load_f()
            # Set to Evaluation Mode
            self.model_f.eval()
            print("Doing Evaluation on the forward model now")
            test_loss = 0
            for j, (geometry, spectra) in enumerate(self.test_loader):  # Loop through the eval set
                if cuda:
                    geometry = geometry.cuda()
                    spectra = spectra.cuda()
                logit = self.model_f(geometry)
                loss = self.make_loss(logit, spectra)  # compute the loss
                test_loss += loss  # Aggregate the loss

            # Record the testing loss to the tensorboard
            test_avg_loss = test_loss.cpu().data.numpy() / (j + 1)
            print("Test loss of forward model loaded is", test_avg_loss)

        """
        Backward Training Part
        """
        print("Now, start Backward Training")
        # Construct optimizer after the model moved to GPU
        self.optm_b = self.make_optimizer_b()
        self.lr_scheduler = self.make_lr_scheduler(self.optm_b)

        for epoch in range(self.flags.train_step):
            # Set to Training Mode
            train_loss = 0
            # boundary_loss = 0                 # Unnecessary during training since we provide geometries
            self.model_b.train()
            self.model_f.train()
            for j, (geometry, spectra) in enumerate(self.train_loader):
                if cuda:
                    geometry = geometry.cuda()  # Put data onto GPU
                    spectra = spectra.cuda()    # Put data onto GPU
                self.optm_b.zero_grad()         # Zero the gradient first
                if self.flags.data_set == 'gaussian_mixture':
                    G_out = self.model_b(spectra.unsqueeze(1))   # Get the geometry prediction
                else:
                    G_out = self.model_b(spectra)  # Get the geometry prediction
                S_out = self.model_f(G_out)     # Get the spectra prediction
                loss = self.make_loss(S_out, spectra, G=G_out)  # Get the loss tensor
                loss.backward()  # Calculate the backward gradients
                self.optm_b.step()  # Move one step the optimizer
                train_loss += loss  # Aggregate the loss
                # boundary_loss += self.Boundary_loss                   # Aggregate the BDY loss

            # Calculate the avg loss of training
            train_avg_loss = train_loss.cpu().data.numpy() / (j + 1)
            # boundary_avg_loss = boundary_loss.cpu().data.numpy() / (j + 1)

            if epoch % self.flags.eval_step == 0:  # For eval steps, do the evaluations and tensor board
                # Record the training loss to the tensorboard
                self.log.add_scalar('Loss/backward_train', train_avg_loss, epoch)
                self.log.add_scalar('Loss/BDY_train', self.Boundary_loss.cpu().data.numpy(), epoch)

                # Set to Evaluation Mode
                self.model_b.eval()
                self.model_f.eval()
                print("Doing Evaluation on the backward model now")
                test_loss = 0
                for j, (geometry, spectra) in enumerate(self.test_loader):  # Loop through the eval set
                    if cuda:
                        geometry = geometry.cuda()
                        spectra = spectra.cuda()
                    if self.flags.data_set == 'gaussian_mixture':
                        G_out = self.model_b(spectra.unsqueeze(1))  # Get the geometry prediction
                    else:
                        G_out = self.model_b(spectra)  # Get the geometry prediction
                    S_out = self.model_f(G_out)  # Get the spectra prediction
                    loss = self.make_loss(S_out, spectra, G=G_out)  # compute the loss
                    test_loss += loss  # Aggregate the loss

                # Record the testing loss to the tensorboard
                test_avg_loss = test_loss.cpu().data.numpy() / (j + 1)
                self.log.add_scalar('Loss/backward_test', test_avg_loss, epoch)
                self.log.add_scalar('Loss/BDY_test', self.Boundary_loss.cpu().data.numpy(), epoch)

                print("This is Epoch %d, training loss %.5f, validation loss %.5f" \
                      % (epoch, train_avg_loss, test_avg_loss))

                # Model improving, save the model down
                if test_avg_loss < self.best_validation_loss:
                    self.best_validation_loss = test_avg_loss
                    self.save_b()
                    print("Saving the model down...")

                    if self.best_validation_loss < self.flags.stop_threshold:
                        print("Training finished EARLIER at epoch %d, reaching loss of %.5f" % \
                              (epoch, self.best_validation_loss))
                        return None

            # Learning rate decay upon plateau
            self.lr_scheduler.step(train_avg_loss)
        self.log.close()
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

