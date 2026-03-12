import numpy as np
from matplotlib.figure import Figure


def show_field(u: np.ndarray):
    fig = Figure(figsize=(5, 4), dpi=120)
    ax = fig.add_subplot(111)
    im = ax.imshow(u, cmap="viridis", origin="lower")
    fig.colorbar(im, ax=ax)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_title("Aether field")
    return fig, ax
