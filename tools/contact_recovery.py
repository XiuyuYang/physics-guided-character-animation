"""Gate recovery on support and match the recorded travel to a run loop."""
import numpy as np


def recovery_start(heights, feet):
    falls = np.flatnonzero(np.asarray(heights) < .45)
    if not len(falls):
        return None
    for i in range(max(int(falls[-1])+8, 7),len(heights)):
        if min(heights[i-7:i+1]) >= .76 and np.ptp(heights[i-7:i+1]) <= .16:
            if np.count_nonzero(np.max(feet[i-5:i+1],axis=1) >= 80) >= 3:
                return i
    return None


def transition_weight(t):
    return t**3 * (10 - 15*t + 6*t*t)


def transition_path(raw, start, end, target_step):
    """Blend frame-to-frame velocity without jumping to the source loop origin."""
    out = raw.copy()
    displacement = np.diff(raw,axis=0)
    for i in range(start+1, len(out)):
        t = min(1.,(i-start)/(end-start))
        w = transition_weight(t)
        # Filter the observed speed only during the middle of the handoff.
        lo, hi = max(0,i-3), min(len(displacement),i+2)
        filtered = np.mean(displacement[lo:hi],axis=0)
        observed = displacement[i-1]*(1-w) + filtered*w
        out[i] = out[i-1] + (1-w)*observed + w*np.array([target_step,0.])
    return out


def matching_phase(source, loop, feet):
    """Choose the run phase whose ankles and toes best match the supported stance."""
    weights = np.repeat(1+np.mean(feet,axis=0)/max(80.,np.mean(feet,axis=0).max()),2)
    candidates = np.arange(len(loop))[:,None]+np.arange(len(source))[None,:]
    error = loop[candidates%len(loop)]-source[None,...]
    return int(np.argmin(np.sum(error**2*weights[None,None,:,None],axis=(1,2,3))))
