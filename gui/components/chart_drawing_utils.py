import typing
from matplotlib.lines import Line2D


def _safe_float_list(values: typing.Iterable) -> list:
    """Convert an iterable of numeric-like values to plain floats, skipping invalid ones."""
    out = []
    for v in values:
        try:
            out.append(float(v))
        except Exception:
            continue
    return out


def prepare_mpf_hlines(horizontal_lines: typing.Iterable[typing.Tuple[float, str, str]],
                       lines: typing.Optional[typing.Any] = None) -> typing.Optional[dict]:
    """Build the `hlines` dictionary that can be passed to mplfinance.plot.

    horizontal_lines: Iterable of (price, color, label)
    lines: Optional external param (list or dict with key 'hlines'). If provided it will be merged.

    Returns: A dict appropriate for `plot_kwargs['hlines']` or None if no lines.
    """
    hlines_prices = []
    hlines_colors = []

    # From stored horizontal_lines
    for price, color, label in (horizontal_lines or []):
        hlines_prices.append(price)
        hlines_colors.append(color)

    # Optionally merge external 'lines' if needed
    if lines is not None:
        if isinstance(lines, dict):
            extra = lines.get("hlines", [])
            if isinstance(extra, (list, tuple)):
                hlines_prices.extend(extra)
        elif isinstance(lines, (list, tuple)):
            hlines_prices.extend(lines)

    if not hlines_prices:
        return None

    safe_hlines = _safe_float_list(hlines_prices)
    if not safe_hlines:
        return None

    colors = hlines_colors if len(hlines_colors) == len(safe_hlines) else "r"

    return dict(
        hlines=safe_hlines,
        colors=colors,
        linestyle="--",
        linewidths=1.5,
        alpha=0.7,
    )


def add_legend_for_hlines(ax, horizontal_lines: typing.Iterable[typing.Tuple[float, str, str]]):
    """Create legend handles for a list of horizontal lines and attach them to ax.

    If there are no horizontal_lines, the legend (if present) is removed.
    """
    # Remove previous legend if present
    legend = getattr(ax, "legend_", None)
    if legend is not None:
        try:
            legend.remove()
        except Exception:
            pass

    if not horizontal_lines:
        return

    handles = []
    labels = []
    for price, color, label in horizontal_lines:
        handles.append(Line2D([], [], color=color, linestyle="--", linewidth=1.5))
        labels.append(label)

    try:
        ax.legend(handles, labels, loc="upper left", fontsize=8)
    except Exception:
        # If legend fails for any reason, just skip it silently
        pass


def add_axhline(ax, price: float, color: str = "r", label: typing.Optional[str] = None,
                linestyle: str = "--", linewidth: float = 1.5, alpha: float = 0.7):
    """Helper to add an axhline to an Axis and return the Line2D object."""
    try:
        line = ax.axhline(y=price, color=color, linestyle=linestyle, linewidth=linewidth, label=label, alpha=alpha)
        return line
    except Exception:
        return None
