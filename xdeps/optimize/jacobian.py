import numpy as np
from ..general import _print

from numpy.linalg import lstsq

class JacobianSolver:

    def __init__(self, func, n_steps_max=20, tol=1e-20, n_bisections=3,
                 min_step=1e-20, verbose=False):
        self.func = func
        self.n_steps_max = n_steps_max
        self.tol = tol
        self.n_bisections = n_bisections
        self.min_step = min_step

        self._penalty_best = None
        self._xbest = None
        self._step = 0
        self.verbose = verbose
        self._penalty_best = 1e200
        self.ncalls = 0
        self.stopped = None
        self._x = None

    @property
    def x(self):
        return self._x

    @x.setter
    def x(self, value):
        # Limit check to be added
        self._x = value
        self.mask_from_limits = np.ones(len(self._x), dtype=bool)

    def step(self, n_steps=1):

        myf = self.func

        for step in range(n_steps):

            self._step += 1

            # test penalty
            y, penalty = self._eval(self.x) # will need to handle mask
            if penalty < self.tol:
                if self.verbose:
                    _print("Jacobian tolerance met")
                    self.stopped = 'tolerance met'
                break
            # Equation search
            jac = myf.get_jacobian(self.x) # will need to handle mask

            # lstsq using only the the variables that were not at the limit
            # in the previous step
            xstep = np.zeros(len(self.x))

            mask_input = self.func.mask_input & self.mask_from_limits
            mask_output = self.func.mask_output.copy()

            xstep[mask_input] = lstsq(
                jac[mask_output, :][:, mask_input], y[mask_output], rcond=None)[0]  # newton step
            self.mask_from_limits[:] = True
            self._last_xstep = xstep.copy()

            newpen = penalty * 2
            alpha = -1

            limits = self.func._get_x_limits()

            while newpen > penalty:  # bisec search
                if alpha > self.n_bisections:
                    break
                alpha += 1
                l = 2.0**-alpha
                if self.verbose:
                    _print(f"\n--> step {step} alpha {alpha}\n")

                this_xstep = l * xstep
                mask_hit_limit = np.zeros(len(self.x), dtype=bool)
                for ii in range(len(self.x)):
                    if self.x[ii] - this_xstep[ii] < limits[ii][0]:
                        this_xstep[ii] = 0
                        mask_hit_limit[ii] = True
                    elif self.x[ii] - this_xstep[ii] > limits[ii][1]:
                        this_xstep[ii] = 0
                        mask_hit_limit[ii] = True

                y, newpen = self._eval(self.x - this_xstep) # will need to handle mask

                self.ncalls += 1
            self.x -= this_xstep  # update solution
            self.mask_from_limits = ~mask_hit_limit

            if self.verbose:
                _print(f"step {step} step_best {self._step_best} {this_xstep}")
            if np.sqrt(np.dot(this_xstep, this_xstep)) < self.min_step:
                if self.verbose:
                    _print("No progress, stopping")
                self.stopped = 'no progress'
                break
        else:
            if self.verbose:
                _print("N. steps reached")

        return self._xbest

    def solve(self, x0):

        self.x = x0.copy()

        self.step(self.n_steps_max)

        return self._xbest

    def _eval(self, x):
        y = self.func(x)
        penalty = np.sqrt(np.dot(y, y))
        if self.verbose:
            _print(f"penalty: {penalty}")
        if penalty < self._penalty_best:
            if self._penalty_best - penalty > 1e-20: #????????????
                self._step_best = self._step
            self._penalty_best = penalty
            self._xbest = x.copy()
            if self.verbose:
                _print(f"new best: {self._penalty_best}")
        return y, penalty

    # def _old_solve(self, x0):

    #     myf = self.func

    #     x0 = np.array(x0, dtype=float)
    #     x = x0.copy()

    #     self._xbest = x0.copy()
    #     self._penalty_best = 1e200
    #     ncalls = 0
    #     info = {}
    #     mask_from_limits = np.ones(len(x0), dtype=bool)
    #     for step in range(self.n_steps_max):

    #         self._step = step
    #         # test penalty
    #         y, penalty = self._eval(x) # will need to handle mask
    #         ncalls += 1
    #         if penalty < self.tol:
    #             if self.verbose:
    #                 _print("Jacobian tolerance met")
    #             break
    #         # Equation search
    #         jac = myf.get_jacobian(x) # will need to handle mask
    #         ncalls += len(x)

    #         # lstsq using only the the variables that were not at the limit
    #         # in the previous step
    #         xstep = np.zeros(len(x))

    #         mask_input = self.func.mask_input & mask_from_limits
    #         mask_output = self.func.mask_output.copy()

    #         xstep[mask_input] = lstsq(
    #             jac[mask_output, :][:, mask_input], y[mask_output], rcond=None)[0]  # newton step
    #         mask_from_limits[:] = True
    #         self._last_xstep = xstep.copy()

    #         newpen = penalty * 2
    #         alpha = -1

    #         limits = self.func._get_x_limits()

    #         while newpen > penalty:  # bisec search
    #             if alpha > self.n_bisections:
    #                 break
    #             alpha += 1
    #             l = 2.0**-alpha
    #             if self.verbose:
    #                 _print(f"\n--> step {step} alpha {alpha}\n")

    #             this_xstep = l * xstep
    #             mask_hit_limit = np.zeros(len(x), dtype=bool)
    #             for ii in range(len(x)):
    #                 if x[ii] - this_xstep[ii] < limits[ii][0]:
    #                     this_xstep[ii] = 0
    #                     mask_hit_limit[ii] = True
    #                 elif x[ii] - this_xstep[ii] > limits[ii][1]:
    #                     this_xstep[ii] = 0
    #                     mask_hit_limit[ii] = True

    #             y, newpen = self._eval(x - this_xstep) # will need to handle mask

    #             self.ncalls += 1
    #         x -= this_xstep  # update solution
    #         mask_from_limits = ~mask_hit_limit

    #         if self.verbose:
    #             _print(f"step {step} step_best {self._step_best} {this_xstep}")
    #         if np.sqrt(np.dot(this_xstep, this_xstep)) < self.min_step:
    #             if self.verbose:
    #                 _print("No progress, stopping")
    #             break
    #     else:
    #         if self.verbose:
    #             _print("Max steps reached")

    #     return self._xbest

