import numpy as np
from ..general import _print

from scipy.optimize import fsolve, minimize
from .jacobian import JacobianSolver


class Vary:
    def __init__(self, name, container, limits=None, step=None, weight=None):

        if weight is None:
            weight = 1.

        if limits is None:
            limits = (-1e200, 1e200)
        else:
            assert len(limits) == 2, '`limits` must have length 2.'

        if step is None:
            step = 1e-10

        assert weight > 0, '`weight` must be positive.'

        self.name = name
        self.limits = np.array(limits)
        self.step = step
        self.weight = weight
        self.container = container
        self.active = True

    def __repr__(self):
        return f'Vary(name={self.name}, limits={self.limits}, step={self.step}, weight={self.weight})'

class VaryList:
    def __init__(self, vars, container, **kwargs):
        self.vary_objects = [Vary(vv, container, **kwargs) for vv in vars]

class Target:
    def __init__(self, tar, value, tol=None, weight=None, scale=None,
                 action=None):

        if scale is not None and weight is not None:
            raise ValueError(
                'Cannot specify both `weight` and `scale` for a target.')

        if scale is not None:
            weight = scale

        self.tar = tar
        self.action = action
        self.value = value
        self.tol = tol
        self.weight = weight
        self._at_index = None
        self.active = True

    def __repr__(self):
        return f'Target(tar={self.tar}, value={self.value}, tol={self.tol}, weight={self.weight})'

    @property
    def scale(self):
        return self.weight

    @scale.setter
    def scale(self, value):
        self.weight = value

    def eval(self, data):
        res = data[self.action]
        if callable(self.tar):
            return self.tar(res)
        else:
            return res[self.tar]

class TargetList:
    def __init__(self, tars, **kwargs):
        self.targets = [Target(tt, **kwargs) for tt in tars]


class TargetInequality(Target):

    def __init__(self, tar, ineq_sign, rhs, tol=None, scale=None):
        super().__init__(tar, value=0, tol=tol, scale=scale)
        assert ineq_sign in ['<', '>'], ('ineq_sign must be either "<" or ">"')
        self.ineq_sign = ineq_sign
        self.rhs = rhs

    def __repr__(self):
        return f'TargetInequality({self.tar} {self.ineq_sign} {self.rhs}, tol={self.tol}, weight={self.weight})'

    def eval(self, tw):
        val = super().eval(tw)
        if self.ineq_sign == '<' and val < self.rhs:
            return 0
        elif self.ineq_sign == '>' and val > self.rhs:
            return 0
        else:
            return val - self.rhs

class Action:
    def prepare(self):
        pass
    def run(self):
        return dict()

class MeritFunctionForMatch:

    def __init__(self, vary, targets, actions, return_scalar,
                 call_counter, verbose, tw_kwargs, steps_for_jacobian):

        self.vary = vary
        self.targets = targets
        self.actions = actions
        self.return_scalar = return_scalar
        self.call_counter = call_counter
        self.verbose = verbose
        self.tw_kwargs = tw_kwargs
        self.steps_for_jacobian = steps_for_jacobian
        self.found_point_within_tolerance = False

    def _x_to_knobs(self, x):
        knob_values = np.array(x).copy()
        for ii, vv in enumerate(self.vary):
            if vv.weight is not None:
                knob_values[ii] *= vv.weight
        return knob_values

    def _knobs_to_x(self, knob_values):
        x = np.array(knob_values).copy()
        for ii, vv in enumerate(self.vary):
            if vv.weight is not None:
                x[ii] /= vv.weight
        return x

    def __call__(self, x):

        _print(f"Matching: model call n. {self.call_counter}       ",
                end='\r', flush=True)
        self.call_counter += 1

        knob_values = self._x_to_knobs(x)

        for vv, val in zip(self.vary, knob_values):
            vv.container[vv.name] = val

        if self.verbose:
            _print(f'x = {knob_values}')

        res_data = {}
        failed = False
        for aa in self.actions:
            res_data[aa] = aa.run()
            if res_data[aa] == 'failed':
                failed = True
                break

        if failed:
            err_values = [1e100 for tt in self.targets]
        else:
            res_values = []
            target_values = []
            for tt in self.targets:
                res_values.append(tt.eval(res_data))
                target_values.append(tt.value)
            self._last_data = res_data # for debugging

            res_values = np.array(res_values)
            target_values = np.array(target_values)
            err_values = res_values - target_values

            if self.verbose:
                _print(f'   f(x) = {res_values}')

            tols = 0 * err_values
            for ii, tt in enumerate(self.targets):
                tols[ii] = tt.tol

            if self.verbose:
                _print(f'   err/tols = {err_values/tols}')

            if np.all(np.abs(err_values) < tols):
                err_values *= 0
                self.found_point_within_tolerance = True
                if self.verbose:
                    _print('Found point within tolerance!')

            for ii, tt in enumerate(self.targets):
                if tt.weight is not None:
                    err_values[ii] *= tt.weight

        if self.return_scalar:
            return np.sum(err_values * err_values)
        else:
            return np.array(err_values)

    def get_jacobian(self, x):
        x = np.array(x).copy()
        steps = self._knobs_to_x(self.steps_for_jacobian)
        assert len(x) == len(steps)
        f0 = self(x)
        if np.isscalar(f0):
            jac = np.zeros((1, len(x)))
        else:
            jac = np.zeros((len(f0), len(x)))
        for ii in range(len(x)):
            x[ii] += steps[ii]
            jac[:, ii] = (self(x) - f0) / steps[ii]
            x[ii] -= steps[ii]
        return jac

    def _get_x_limits(self):
        knob_limits = []
        for vv in self.vary:
            knob_limits.append(vv.limits)
        knob_limits = np.array(knob_limits)
        x_lim_low = self._knobs_to_x(np.atleast_1d(np.squeeze(knob_limits[:, 0])))
        x_lim_high = self._knobs_to_x(np.atleast_1d(np.squeeze(knob_limits[:, 1])))
        x_limits = [(hh, ll) for hh, ll in zip(x_lim_low, x_lim_high)]
        return x_limits

    @property
    def mask_input(self):
        mask = []
        for vv in self.vary:
            if hasattr(vv, 'active'):
                mask.append(vv.active)
            else:
                mask.append(True)
        return np.array(mask)

    @property
    def mask_output(self):
        mask = []
        for tt in self.targets:
            if hasattr(tt, 'active'):
                mask.append(tt.active)
            else:
                mask.append(True)
        return np.array(mask)

class Optimize:

    def __init__(self, vary, targets, restore_if_fail=True,
                 solver=None,
                 verbose=False, assert_within_tol=True,
                 n_steps_max=20,
                 solver_options={}, **kwargs):

        if isinstance(vary, (str, Vary)):
            vary = [vary]

        input_vary = vary
        vary = []
        for ii, rr in enumerate(input_vary):
            if isinstance(rr, Vary):
                vary.append(rr)
            elif isinstance(rr, str):
                vary.append(Vary(rr))
            elif isinstance(rr, (list, tuple)):
                raise ValueError('Not supported')
            elif isinstance(rr, VaryList):
                vary += rr.vary_objects
            else:
                raise ValueError(f'Invalid vary setting {rr}')

        input_targets = targets
        targets = []
        for ii, tt in enumerate(input_targets):
            if isinstance(tt, Target):
                targets.append(tt)
            elif isinstance(tt, (list, tuple)):
                targets.append(Target(*tt))
            elif isinstance(tt, TargetList):
                targets += tt.targets
            else:
                raise ValueError(f'Invalid target element {tt}')

        actions = []
        for tt in targets:
            if tt.weight is None:
                tt.weight = 1.
            if tt.weight <= 0:
                raise ValueError('`weight` must be positive.')

            if tt.action not in actions:
                actions.append(tt.action)

        for aa in actions:
            aa.prepare()

        data0 = {}
        for aa in actions:
            data0[aa] = aa.run()
            assert data0[aa] != 'failed', (
                f'Action {aa} failed to compute initial data.')

        for tt in targets:
            if tt.value == 'preserve':
                tt.value = tt.eval(data0)

        if solver is None:
            solver = 'jacobian'

        if verbose:
            _print(f'Using solver {solver}')

        steps = []
        for vv in vary:
            steps.append(vv.step)

        assert solver in ['fsolve', 'bfgs', 'jacobian'], (
                        f'Invalid solver {solver}.')

        return_scalar = {'fsolve': False, 'bfgs': True, 'jacobian': False}[solver]

        _err = MeritFunctionForMatch(
                    vary=vary, targets=targets,
                    actions=actions,
                    return_scalar=return_scalar, call_counter=0, verbose=verbose,
                    tw_kwargs=kwargs, steps_for_jacobian=steps)

        if solver == 'jacobian':
            self.solver = JacobianSolver(
                func=_err, verbose=verbose,
                **solver_options)
        else:
            raise NotImplementedError(
                f'Solver {solver} not implemented.')

        self.assert_within_tol = assert_within_tol
        self.restore_if_fail = restore_if_fail
        self.n_steps_max = n_steps_max
        self.log = []

    @property
    def _err(self):
        return self.solver.func

    @property
    def verbose(self):
        return self.solver.verbose

    @verbose.setter
    def verbose(self, value):
        self.solver.verbose = value

    def show(self, vary=True, targets=True):
        if vary:
            print('Vary:')
            for ii, vv in enumerate(self.vary):
                state = '(ON)' if vv.active else '(OFF)'
                print(f'{ii:<2} {state:<5}:  {vv}')
        if targets:
            print('Targets:')
            for ii, tt in enumerate(self.targets):
                state = '(ON)' if tt.active else '(OFF)'
                print(f'{ii:<2} {state:<5}:  {tt}')

    @property
    def vary(self):
        return self._err.vary

    @property
    def targets(self):
        return self._err.targets

    def _extract_knob_values(self):
        res = []
        for vv in self.vary:
            val = vv.container[vv.name]
            if hasattr(val, '_value'):
                res.append(val._value)
            else:
                res.append(val)
        return res

    def step(self, n_steps=1):

        knobs_before = self._extract_knob_values()
        self.log.append(knobs_before)
        x = self._err._knobs_to_x(knobs_before)
        if self.solver.x is None or not np.allclose(x, self.solver.x, rtol=0, atol=1e-12):
            self.solver.x = x

        # self.solver.x = self._err._knobs_to_x(self._extract_knob_values())
        self.solver.step(n_steps=n_steps)

        for vv, rr in zip(self.vary, self._err._x_to_knobs(self.solver.x)):
            vv.container[vv.name] = rr

    def solve(self):
        self.solver.x = self._err._knobs_to_x(self._extract_knob_values())
        for ii in range(self.n_steps_max):
            self.step()
            if self.solver.stopped is not None:
                break

        result_info = {'res': self.solver._xbest}
        return result_info

    def old_solve(self):

        x0 = self._err._knobs_to_x(self._extract_knob_values())
        try:
            res = self.solver.solve(x0=x0.copy())
            result_info = {'res': res}

            # Old implementation based on scipy.optimize (kept for possible future use)
            # if self.solver == 'fsolve':
            #     raise NotImplementedError # Untested
            #     (res, infodict, ier, mesg) = fsolve(self._err, x0=x0.copy(),
            #         full_output=True, fprime=self._jac)
            #     if ier != 1:
            #         raise RuntimeError("fsolve failed: %s" % mesg)
            #     result_info = {
            #         'res': res, 'info': infodict, 'ier': ier, 'mesg': mesg}
            # elif self.solver == 'bfgs':
            #     raise NotImplementedError # Untested
            #     optimize_result = minimize(self._err, x0=x0.copy(), method='L-BFGS-B',
            #                 bounds=self.x_limits,
            #                 jac=self._jac, options={'gtol':0})
            #     result_info = {'optimize_result': optimize_result}
            #     res = optimize_result.x


            if self.assert_within_tol and not self._err.found_point_within_tolerance:
                raise RuntimeError('Could not find point within tolerance.')

            for vv, rr in zip(self.vary, self._err._x_to_knobs(res)):
                vv.container[vv.name] = rr
        except Exception as err:
            if self.restore_if_fail:
                knob_values0 = self._err._x_to_knobs(x0)
                for ii, vv in enumerate(self.vary):
                    vv.container[vv.name] = knob_values0[ii]
            _print('\n')
            raise err
        _print('\n')
        return result_info

