"""
EnsembleKalmanFilter.py
@author: ksuchak1990
date_created: 19/04/10
A class to represent a general Ensemble Kalman Filter for use with StationSim.
"""
# Imports
import warnings as warns
import numpy as np
import matplotlib.pyplot as plt
from copy import deepcopy

# Classes
class EnsembleKalmanFilter:
    """
    A class to represent a general EnKF.
    """
    def __init__(self, model, filter_params, model_params):
        """
        Initialise the Ensemble Kalman Filter.

        Params:
            model
            filter_params
            model_params

        Returns:
            None
        """
        self.time = 0

        # Ensure that model has correct attributes
        assert self.is_good_model(model), 'Model missing attributes.'

        # Filter attributes - outlines the expected params
        self.max_iterations = None
        self.ensemble_size = None
        self.assimilation_period = None
        self.state_vector_length = None
        self.data_vector_length = None
        self.H = None
        self.R_vector = None
        self.data_covariance = None
        self.base_model = model(model_params)

        # Get filter attributes from params, warn if unexpected attribute
        for k, v in filter_params.items():
            if not hasattr(self, k):
                w = 'EnKF received unexpected {0} attribute.'.format(k) 
                warns.warn(w, RuntimeWarning)
            setattr(self, k, v)

        # Set up ensemble of models
        self.models = [deepcopy(self.base_model) for _ in range(self.ensemble_size)]

        # Make sure that models have state
        for m in self.models:
            if not hasattr(m, 'state'):
                raise AttributeError("Model has no 'state' attribute.")

        # We're going to need H.T very often, so just do it once and store
        self.H_transpose = self.H.T

        # Make sure that we have a data covariance matrix
        """
        https://arxiv.org/pdf/0901.3725.pdf -
        The covariance matrix R describes the estimate of the error of the data; if
        the random errors in the entries of the data vector d are independent,R is
        diagonal and its diagonal entries are the squares of the standard
        deviation (“error size”) of the error of the corresponding entries of the
        data vector d.
        """
        if not self.data_covariance:
            self.data_covariance = np.diag(self.R_vector)

        # Create placeholders for ensembles
        self.state_ensemble = np.zeros(shape=(self.state_vector_length,
                                              self.ensemble_size))
        self.state_mean = None
        self.data_ensemble = np.zeros(shape=(self.data_vector_length,
                                             self.ensemble_size))

        self.update_state_ensemble()
        self.update_state_mean()
        self.results = list()
#        self.results = [self.state_mean]
        print('Running Ensemble Kalman Filter...')
        print('max_iterations:\t{0}'.format(self.max_iterations))
        print('ensemble_size:\t{0}'.format(self.ensemble_size))
        print('assimilation_period:\t{0}'.format(self.assimilation_period))

    def step(self):
        """
        Step the filter forward by one time-step.

        Params:
            data

        Returns:
            None
        """
        self.predict()
        self.update_state_ensemble()
        self.update_state_mean()
        if self.time % self.assimilation_period == 0:
            self.plot_model('before update {0}'.format(self.time))
            data = self.base_model.state_history[-1]
            self.update(data)
            self.update_models()
            self.plot_model('after update {0}'.format(self.time))
        self.time += 1
        self.update_state_mean()
        self.results.append(self.state_mean)

    def predict(self):
        """
        Step the model forward by one time-step to produce a prediction.

        Params:

        Returns:
            None
        """
        self.base_model.step()
        for i in range(self.ensemble_size):
            self.models[i].step()

    def update(self, data):
        """
        Update filter with data provided.

        Params:
            data

        Returns:
            None
        """
        if len(data) != self.data_vector_length:
            w = 'len(data)={0}, expected {1}'.format(len(data),
                                                     self.data_vector_length)
            warns.warn(w, RuntimeWarning)
        X = np.zeros(shape=(self.state_vector_length, self.ensemble_size))
        gain_matrix = self.make_gain_matrix()
        self.update_data_ensemble(data)
        diff = self.data_ensemble - self.H @ self.state_ensemble
        X = self.state_ensemble + gain_matrix @ diff
        self.state_ensemble = X

    def update_state_ensemble(self):
        """
        Update self.state_ensemble based on the states of the models.
        """
        for i in range(self.ensemble_size):
            self.state_ensemble[:, i] = self.models[i].state

    def update_state_mean(self):
        """
        Update self.state_mean based on the current state ensemble.
        """
        self.state_mean = np.mean(self.state_ensemble, axis=1)

    def update_data_ensemble(self, data):
        """
        Create perturbed data vector.
        I.e. a replicate of the data vector plus normal random n-d vector.
        R - data covariance; this should be either a number or a vector with
        same length as the data.
        """
        x = np.zeros(shape=(len(data), self.ensemble_size))
        for i in range(self.ensemble_size):
            x[:, i] = data + np.random.normal(0, self.R_vector, len(data))
        self.data_ensemble = x

    def update_models(self):
        """
        Update individual model states based on state ensemble.
        """
        for i in range(self.ensemble_size):
            self.models[i].state = self.state_ensemble[:, i]

    def make_ensemble_covariance(self):
        """
        Create ensemble covariance matrix.
        """
        a = self.state_ensemble @ np.ones(shape=(self.ensemble_size, 1))
        b = np.ones(shape=(1, self.ensemble_size))
        A = self.state_ensemble - 1/self.ensemble_size * a @ b
        return 1/(self.ensemble_size - 1) * A @ A.T

    def make_gain_matrix(self):
        """
        Create kalman gain matrix.
        """
        """
        Version from Gillijns, Barrero Mendoza, etc.
        # Find state mean and data mean
        data_mean = np.mean(self.data_ensemble, axis=1)

        # Find state error and data error matrices
        state_error = np.zeros(shape=(self.state_vector_length,
                                      self.ensemble_size))
        data_error = np.zeros(shape=(self.data_vector_length,
                                     self.ensemble_size))
        for i in range(self.ensemble_size):
            state_error[:, i] = self.state_ensemble[:, i] - self.state_mean
            data_error[:, i] = self.data_ensemble[:, i] - data_mean
        P_x = 1 / (self.ensemble_size - 1) * state_error @ state_error.T
        P_xy = 1 / (self.ensemble_size - 1) * state_error @ data_error.T
        P_y = 1 / (self.ensemble_size -1) * data_error @ data_error.T
        K = P_xy @ np.linalg.inv(P_y)
        return K
        """
        """
        More standard version
        """
        C = np.cov(self.state_ensemble)
        state_covariance = self.H @ C @ self.H_transpose
        diff = state_covariance + self.data_covariance
        return C @ self.H_transpose @ np.linalg.inv(diff)

    @classmethod
    def is_good_model(cls, model):
        """
        A utility function to ensure that we've been provided with a good model.
        This means that the model should have the following:
        - step (method)
        - state (attribute)
        - set_state (method)
        - set_state (method)

        Params:
            model

        Returns:
            boolean
        """
        methods = ['step', 'set_state', 'get_state']
        attribute = 'state'
        has_methods = [cls.has_method(model, m) for m in methods]
#        b = all(has_methods) and hasattr(model, attribute)
        b = all(has_methods)
        return b

    @staticmethod
    def has_method(model, method):
        """
        Check that a model has a given method.
        """
        b = True
        try:
            m = getattr(model, method)
            if not callable(m):
                w = "Model {} not callable".format(method)
                warns.warn(w, RuntimeWarning)
                b = False
        except:
            w = "Model doesn't have {}".format(method)
            warns.warn(w, RuntimeWarning)
            b = False
        return b

    @staticmethod
    def separate_coords(arr):
        """
        Function to split a flat array into xs and ys.
        Assumes that xs and ys alternate.
        """
        return arr[::2], arr[1::2]

    def plot_model(self, title_str):
        """
        Plot base_model and ensemble members.
        """
        # Get coords
        base_x, base_y = self.separate_coords(self.base_model.state)

        # Plot agents
        plt.figure()
        plt.xlim(0, self.base_model.width)
        plt.ylim(0, self.base_model.height)
        plt.title(title_str)
        plt.scatter(base_x, base_y)

        # Plot ensemble members
        for model in self.models:
            xs, ys = self.separate_coords(model.state)
            plt.scatter(xs, ys, s=1, color='red')

        # Finish fig
        plt.show()

    def process_results(self):
        """
        Method to process ensemble results, comparing against truth.
        Calculate x-error and y-error for each agent at each timestep,
        average over all agents, and plot how average errors vary over time.
        """
        x_mean_errors = list()
        y_mean_errors = list()
        distance_mean_errors = list()
        truth = self.base_model.state_history

        for i, result in enumerate(self.results):
            distance_error, x_error, y_error = self.make_errors(result, truth[i])
            x_mean_errors.append(np.mean(x_error))
            y_mean_errors.append(np.mean(y_error))
            distance_mean_errors.append(np.mean(distance_error))

        self.plot_results(distance_mean_errors, x_mean_errors, y_mean_errors)

    def make_errors(self, result, truth):
        """
        Method to calculate x-errors and y-errors
        """
        x_result, y_result = self.separate_coords(result)
        x_truth, y_truth = self.separate_coords(truth)

        x_error = np.abs(x_result - x_truth)
        y_error = np.abs(y_result - y_truth)
        distance_error = np.sqrt(np.square(x_error) + np.square(y_error))

        return distance_error, x_error, y_error

    @staticmethod
    def plot_results(distance_errors, x_errors, y_errors):
        """
        Method to plot the evolution of errors in the filter.
        """
        plt.figure()
        plt.scatter(range(len(distance_errors)), distance_errors,
                    label='$\mu$', s=1)
        plt.scatter(range(len(x_errors)), x_errors, label='$\mu_x$', s=1)
        plt.scatter(range(len(y_errors)), y_errors, label='$\mu_y$', s=1)
        plt.xlabel('Time')
        plt.ylabel('Mean absolute error')
        plt.legend()
        plt.show()

