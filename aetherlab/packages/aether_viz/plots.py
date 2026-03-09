import matplotlib.pyplot as plt
import numpy as np


def show_field(u: np.ndarray):
    fig, ax = plt.subplots()
    im = ax.imshow(u, cmap="viridis", origin="lower")
    fig.colorbar(im, ax=ax)
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_title("Aether field")
    return fig, ax
