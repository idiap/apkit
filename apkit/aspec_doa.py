"""
aspec_doa.py

Angular spectrum-based DOA estimation

Copyright (c) 2017 Idiap Research Institute, http://www.idiap.ch/
Written by Weipeng He <weipeng.he@idiap.ch>
"""

import sys
import math

import numpy as np
import scipy.interpolate

from .basic import steering_vector, compute_delay
from .doa import azimuth_distance

def phi_mvdr_snr(ecov, delay, fbins=None):
    """Local angular spectrum function: MVDR (SNR)

    Args:
        ecov  : empirical covariance matrix, indices (cctf)
        delay : the set of delays to probe, indices (dc)
        fbins : (default None) if fbins is not over all frequencies,
                use fins to specify centers of frequency bins as discrete
                values.

    Returns:
        phi   : local angular spectrum function, indices (dt),
                here 'd' is the index of delay
    """
    # compute inverse of empirical covariance matrix
    eta = 1e-10
    nch, _, nframe, nfbin = ecov.shape
    iecov = np.zeros(ecov.shape, dtype=ecov.dtype)
    for i in xrange(nframe):
        for j in xrange(nfbin):
            iecov[:,:,i,j] = np.asmatrix(ecov[:,:,i,j] + np.eye(nch) * eta).I

    # total power: trace mean
    tpow = np.einsum('cctf->tf', ecov).real / nch + eta

    phi = np.zeros((len(delay), nframe))
    for i in xrange(len(delay)):
        if fbins is None:
            stv = steering_vector(delay[i], nfbin)
        else:
            stv = steering_vector(delay[i], fbins=fbins)
        denom = np.einsum('cf,cdtf,df->tf', stv.conj(), iecov, stv, optimize='optimal').real
        assert np.all(denom > 0)                    # iecov positive definite
        isnr = np.maximum(tpow * denom - 1.0, eta)  # 1 / snr
        phi[i] = np.sum(1. / isnr, axis=1) / nfbin  # average over frequency

    return phi

def phi_mvdr(ecov, delay, fbins=None):
    """Local angular spectrum function: MVDR

    Args:
        ecov  : empirical covariance matrix, indices (cctf)
        delay : the set of delays to probe, indices (dc)
        fbins : (default None) if fbins is not over all frequencies,
                use fins to specify centers of frequency bins as discrete
                values.

    Returns:
        phi   : local angular spectrum function, indices (dt),
                here 'd' is the index of delay
    """
    # compute inverse of empirical covariance matrix
    eta = 1e-10
    nch, _, nframe, nfbin = ecov.shape
    iecov = np.zeros(ecov.shape, dtype=ecov.dtype)
    for i in xrange(nframe):
        for j in xrange(nfbin):
            iecov[:,:,i,j] = np.asmatrix(ecov[:,:,i,j] + np.eye(nch) * eta).I

    phi = np.zeros((len(delay), nframe))
    for i in xrange(len(delay)):
        if fbins is None:
            stv = steering_vector(delay[i], nfbin)
        else:
            stv = steering_vector(delay[i], fbins=fbins)
        denom = np.einsum('cf,cdtf,df->tf', stv.conj(), iecov, stv, optimize='optimal').real
        assert np.all(denom > 0)            # iecov positive definite
        phi[i] = np.sum(1. / denom, axis=1) # sum over frequency

    return phi

def phi_srp_phat(ecov, delay, fbins=None):
    """Local angular spectrum function: SRP-PHAT

    Args:
        ecov  : empirical covariance matrix, indices (cctf)
        delay : the set of delays to probe, indices (dc)
        fbins : (default None) if fbins is not over all frequencies,
                use fins to specify centers of frequency bins as discrete
                values.

    Returns:
        phi   : local angular spectrum function, indices (dt),
                here 'd' is the index of delay
    """
    # compute inverse of empirical covariance matrix
    nch, _, nframe, nfbin = ecov.shape

    mask = np.asarray([[c < d for d in xrange(nch)] for c in xrange(nch)])
    ecov_upper_tri = ecov[mask]
    cpsd_phat = np.zeros(ecov_upper_tri.shape, dtype=ecov_upper_tri.dtype)
    ampl = np.abs(ecov_upper_tri)
    non_zero_mask = ampl > 1e-20
    cpsd_phat[non_zero_mask] = ecov_upper_tri[non_zero_mask] / ampl[non_zero_mask]

    phi = np.zeros((len(delay), nframe))
    for i in xrange(len(delay)):
        if fbins is None:
            stv = steering_vector(delay[i], nfbin)
        else:
            stv = steering_vector(delay[i], fbins=fbins)

        x = np.asarray([stv[c] * stv[d].conj() for c in xrange(nch)
                                               for d in xrange (nch)
                                               if c < d])
        phi[i] = np.einsum('itf,if->t', cpsd_phat, x.conj(),
                           optimize='optimal').real / nfbin / len(x)
    return phi

def phi_srp_phat_nonlin(ecov, delay, fbins=None):
    """Local angular spectrum function: SRP-PHAT non-linear

    Args:
        ecov  : empirical covariance matrix, indices (cctf)
        delay : the set of delays to probe, indices (dc)
        fbins : (default None) if fbins is not over all frequencies,
                use fins to specify centers of frequency bins as discrete
                values.

    Returns:
        phi   : local angular spectrum function, indices (dt),
                here 'd' is the index of delay
    """
    # compute inverse of empirical covariance matrix
    nch, _, nframe, nfbin = ecov.shape

    mask = np.asarray([[c < d for d in xrange(nch)] for c in xrange(nch)])
    ecov_upper_tri = ecov[mask]
    cpsd_phat = np.zeros(ecov_upper_tri.shape, dtype=ecov_upper_tri.dtype)
    ampl = np.abs(ecov_upper_tri)
    non_zero_mask = ampl > 1e-20
    cpsd_phat[non_zero_mask] = ecov_upper_tri[non_zero_mask] / ampl[non_zero_mask]

    phi = np.zeros((len(delay), nframe))
    for i in xrange(len(delay)):
        if fbins is None:
            stv = steering_vector(delay[i], nfbin)
        else:
            stv = steering_vector(delay[i], fbins=fbins)

        x = np.asarray([stv[c] * stv[d].conj() for c in xrange(nch)
                                               for d in xrange (nch)
                                               if c < d])
        phi_if = np.einsum('itf,if->itf', cpsd_phat, x.conj(),
                           optimize='optimal').real
        phi_nonlin = 1 - np.tanh(2 * np.sqrt(1 - np.minimum(phi_if, 1.0)))
        phi[i] = np.einsum('itf->t', phi_nonlin, optimize='optimal') / nfbin / len(x)
    return phi

class MVDR_NCOV:
    """MVDR with known noise covariance matrix"""

    def __init__(self, ncov):
        """
        Args:
            ncov : noise spatial covariance matrix, indexed by (ccf)
        """
        self.incov = np.moveaxis(np.linalg.inv(np.moveaxis(ncov, 2, 0)),
                                 0, 2)

    def __call__(self, ecov, delay, fbins=None):
        """Local angular spectrum function: MVDR-NCOV

        Args:
            ecov  : empirical covariance matrix, indices (cctf)
            delay : the set of delays to probe, indices (dc)
            fbins : (default None) if fbins is not over all frequencies,
                    use fins to specify centers of frequency bins as discrete
                    values.

        Returns:
            phi   : local angular spectrum function, indices (dt),
                    here 'd' is the index of delay
        """
        nch, _, nframe, nfbin = ecov.shape
        phi = np.zeros((len(delay), nframe))
        for i in xrange(len(delay)):
            if fbins is None:
                stv = steering_vector(delay[i], nfbin)
            else:
                stv = steering_vector(delay[i], fbins=fbins)
            w = np.einsum('cdf,df->cf', self.incov, stv)
            n = np.einsum('cf,cf->f', stv.conj(), w)
            w = np.einsum('cf,f->cf', w, 1.0 / n)
            phi[i] = np.einsum('cf,cdtf,df->t', w.conj(), ecov, w,
                               optimize='optimal').real

        return phi

class MVDR_NCOV_SNR:
    """MVDR with known noise covariance matrix"""

    def __init__(self, ncov):
        """
        Args:
            ncov : noise spatial covariance matrix, indexed by (ccf)
        """
        self.incov = np.moveaxis(np.linalg.inv(np.moveaxis(ncov, 2, 0)),
                                 0, 2)

    def __call__(self, ecov, delay, fbins=None):
        """Local angular spectrum function: MVDR-NCOV

        Args:
            ecov  : empirical covariance matrix, indices (cctf)
            delay : the set of delays to probe, indices (dc)
            fbins : (default None) if fbins is not over all frequencies,
                    use fins to specify centers of frequency bins as discrete
                    values.

        Returns:
            phi   : local angular spectrum function, indices (dt),
                    here 'd' is the index of delay
        """
        nch, _, nframe, nfbin = ecov.shape
        phi = np.zeros((len(delay), nframe))

        # total power
        pt = np.einsum('cctf->tf', ecov).real

        for i in xrange(len(delay)):
            if fbins is None:
                stv = steering_vector(delay[i], nfbin)
            else:
                stv = steering_vector(delay[i], fbins=fbins)
            w = np.einsum('cdf,df->cf', self.incov, stv)
            pn = 1.0 / np.einsum('cf,cf->f', stv.conj(), w).real
            # beamformer weight
            w = np.einsum('cf,f->cf', w, pn)
            # signal power
            ps = np.einsum('cf,cdtf,df->tf', w.conj(), ecov, w,
                           optimize='optimal').real
            # residual power
            pn = np.maximum(pt - ps, 1e-10)
            # snr
            phi[i] = np.einsum('tf,tf->t', ps, 1.0 / pn)

        return phi

class MVDR_NCOV_SIG:
    """MVDR with known noise covariance matrix"""

    def __init__(self, ncov):
        """
        Args:
            ncov : noise spatial covariance matrix, indexed by (ccf)
        """
        self.incov = np.moveaxis(np.linalg.inv(np.moveaxis(ncov, 2, 0)),
                                 0, 2)

    def __call__(self, ecov, delay, fbins=None):
        """Local angular spectrum function: MVDR-NCOV

        Args:
            ecov  : empirical covariance matrix, indices (cctf)
            delay : the set of delays to probe, indices (dc)
            fbins : (default None) if fbins is not over all frequencies,
                    use fins to specify centers of frequency bins as discrete
                    values.

        Returns:
            phi   : local angular spectrum function, indices (dt),
                    here 'd' is the index of delay
        """
        nch, _, nframe, nfbin = ecov.shape
        phi = np.zeros((len(delay), nframe))
        for i in xrange(len(delay)):
            if fbins is None:
                stv = steering_vector(delay[i], nfbin)
            else:
                stv = steering_vector(delay[i], fbins=fbins)
            w = np.einsum('cdf,df->cf', self.incov, stv)
            # noise power
            pn = 1.0 / np.einsum('cf,cf->f', stv.conj(), w).real
            # beamformer weight
            w = np.einsum('cf,f->cf', w, pn)
            # total power
            pt = np.einsum('cf,cdtf,df->tf', w.conj(), ecov, w,
                           optimize='optimal').real
            # signal power
            ps = pt - pn
            # snr
            phi[i] = np.einsum('tf->t', ps)

        return phi


def sevd_music(ecov, delay, fbins=None):
    """Local angular spectrum function: SEVD-MUSIC

    Args:
        ecov  : empirical covariance matrix, indices (cctf)
        delay : the set of delays to probe, indices (dc)
        fbins : (default None) if fbins is not over all frequencies,
                use fins to specify centers of frequency bins as discrete
                values.

    Returns:
        phi   : local angular spectrum function, indices (dt),
                here 'd' is the index of delay
    """
    nch, _, nframe, nfbin = ecov.shape
    phi = np.zeros((len(delay), nframe))
    for t in xrange(nframe):
        w, v = np.linalg.eigh(np.moveaxis(ecov[:,:,t], 2, 0))
        v = v[:,:,:-1]   # assume one source

        for i in xrange(len(delay)):
            if fbins is None:
                stv = steering_vector(delay[i], nfbin)
            else:
                stv = steering_vector(delay[i], fbins=fbins)
            x = np.einsum('fcd,cf->df', v.conj(), stv)
            xx = np.einsum('df,df->f', x.conj(), x).real
            phi[i,t] = np.sum(1.0 * nch / xx)

    return phi

class MUSIC:
    """MUSIC"""

    def __init__(self, ncov):
        """
        Args:
            ncov : noise spatial covariance matrix, indexed by (ccf)
        """
        self.ncov = ncov

    def __call__(self, ecov, delay, fbins=None):
        """Local angular spectrum function: MUSIC

        Args:
            ecov  : empirical covariance matrix, indices (cctf)
            delay : the set of delays to probe, indices (dc)
            fbins : (default None) if fbins is not over all frequencies,
                    use fins to specify centers of frequency bins as discrete
                    values.

        Returns:
            phi   : local angular spectrum function, indices (dt),
                    here 'd' is the index of delay
        """
        nch, _, nframe, nfbin = ecov.shape
        phi = np.zeros((len(delay), nframe))
        for t in xrange(nframe):
            neigs=np.zeros((nfbin, nch, nch-1), dtype=ecov.dtype)
            for f in xrange(nfbin):
                w, v = scipy.linalg.eigh(ecov[:,:,t,f], self.ncov[:,:,f],
                                         eigvals=(0, nch-2))
                neigs[f] = v / np.linalg.norm(v, axis=0, keepdims=True)

            for i in xrange(len(delay)):
                if fbins is None:
                    stv = steering_vector(delay[i], nfbin)
                else:
                    stv = steering_vector(delay[i], fbins=fbins)
                x = np.einsum('fcd,cf->df', neigs.conj(), stv)
                xx = np.einsum('df,df->f', x.conj(), x).real
                phi[i,t] = np.sum(1.0 * nch / xx)

        return phi

class GSVD_MUSIC:
    """GSVD-MUSIC"""

    def __init__(self, ncov):
        """
        Args:
            ncov : noise spatial covariance matrix, indexed by (ccf)
        """
        self.incov = np.moveaxis(np.linalg.inv(np.moveaxis(ncov, 2, 0)),
                                 0, 2)

    def __call__(self, ecov, delay, fbins=None):
        """Local angular spectrum function: GSVD-MUSIC

        Args:
            ecov  : empirical covariance matrix, indices (cctf)
            delay : the set of delays to probe, indices (dc)
            fbins : (default None) if fbins is not over all frequencies,
                    use fins to specify centers of frequency bins as discrete
                    values.

        Returns:
            phi   : local angular spectrum function, indices (dt),
                    here 'd' is the index of delay
        """
        nch, _, nframe, nfbin = ecov.shape
        phi = np.zeros((len(delay), nframe))
        for t in xrange(nframe):
            u, s, v = np.linalg.svd(np.einsum('cdf,def->fce', self.incov, ecov[:,:,t,:]))
            u = u[:,:,1:]   # assume one source

            for i in xrange(len(delay)):
                if fbins is None:
                    stv = steering_vector(delay[i], nfbin)
                else:
                    stv = steering_vector(delay[i], fbins=fbins)
                x = np.einsum('fcd,cf->df', u.conj(), stv)
                xx = np.einsum('df,df->f', x.conj(), x).real
                phi[i,t] = np.sum(1.0 * nch / xx)

        return phi

def local_maxima(phi, nlist, th_phi=0.0):
    """Find local maxima

    Args:
        phi    : local angular spectrum function, indices (dt),
                 here 'd' is the index of delay
        nlist  : list of list of neighbor indices
        th_phi : the score of local maxima should exceed the threshold

    Returns:
        lmax   : list of local maxima indices, indexed by time.
    """
    ndoa, nframe = phi.shape
    lmax = []
    for pf in phi.T:
        lmf = []
        ph_sort = sorted(enumerate(pf), key=(lambda x : x[1]), reverse=True)
        ig_set = set()
        for i, p in ph_sort:
            if p <= th_phi:
                break
            if i not in ig_set:
                is_max = True
                for n in nlist[i]:
                    if p < pf[n]:
                        is_max = False
                        break
                if is_max:
                    lmf.append(i)
                ig_set.update(nlist[i])
        lmax.append(lmf)
    return lmax

def merge_lm_on_azimuth(phi, lmax, doa, th_azi):
    """Find local maxima

    Args:
        phi    : local angular spectrum function, indices (dt),
                 here 'd' is the index of delay
        lmax   : list of local maxima indices, indexed by time.
        doa    : set of DOA associated with phi
        th_azi : neighbor distance in azimuth direction

    Returns:
        lmax   : refined local maxima
    """
    # TODO: chain effect

    ndoa, nframe = phi.shape
    nlmax = []

    for t in xrange(nframe):
        # remove elevation > 70 degrees
        l = np.asarray([x for x in lmax[t]
                          if abs(doa[x][2]) < math.sin(math.pi / 180 * 70)])
        n = len(l)
        m = np.ones(n, dtype=bool)
        for i in xrange(n - 1):
            for j in xrange(i + 1, n):
                # TODO
                ad = azimuth_distance(doa[l[i]], doa[l[j]])
                if ad < th_azi:
                    if phi[l[i], t] >= phi[l[j], t]:
                        m[j] = False
                    else:
                        m[i] = False
        nlmax.append(list(l[m]))
    return nlmax

def convert_to_azimuth(phi, doa, agrid, egrid, m_pos):
    """Convert LASF to a function of azimuth by finding the maximum across elevation.

    Args:
        phi   : local angular spectrum function, indices (dt),
                here 'd' is the index of delay
        doa   : set of DOA associated with phi
        agrid : azimuth grid (rad)
        egrid : elevation grid (rad)
        m_pos : microphone positions, (M,3) array,
                M is number of microphones.

    Return    :
        phi_a : phi on azimuth grid, indexed by 'ta',
                'a' is the azimuth index
    """
    ndoa, nframe = phi.shape
    phi_a = np.zeros((nframe, len(agrid)))

    # delay on data points (doa)
    delay = compute_delay(m_pos, doa)

    # DOAs on grid
    gdoa = [[(math.cos(e)*math.cos(a),
              math.cos(e)*math.sin(a),
              math.sin(e)) for e in egrid] for a in agrid]

    # delay on grid
    gdelay = [compute_delay(m_pos, d) for d in gdoa]

    # iterate through frames
    for t in xrange(nframe):
        print >> sys.stderr, 'frame %d' % t
        # create interpolated function
        phi_intp = scipy.interpolate.Rbf(delay[:,1], delay[:,2],
                                         delay[:,3], phi[:,t],
                                         function='thin_plate')
        # interpolate on each azimuth direction
        for i, d in enumerate(gdelay):
            # interpolate
            p = phi_intp(d[:,1], d[:,2], d[:,3])

            # max pooling
            phi_a[t,i] = np.max(p)

    return phi_a

# -*- Mode: Python -*-
# vi:si:et:sw=4:sts=4:ts=4

