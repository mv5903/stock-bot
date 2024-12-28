import io

import matplotlib.pyplot as plt
import pandas as pd


def dataframe_to_image(
    df: pd.DataFrame,
    highlight_column: str,
    money_cols: list = [str],
    color_positive="green",
    color_negative="red",
    background_color="#2b2b2b",  # Muted background color
    text_color="white",  # Default text color
    figure_background_color="black",  # Background outside the table
) -> io.BytesIO:
    """
    Convert a DataFrame to an image and return the image as a BytesIO buffer.

    Args:
        `df`: The `DataFrame` to convert to an image
        `highlight_column` (optional): The column to color text based on the value based on `color_positive` and `color_negative` values
        `money_cols` (optional): A list of columns to format as money. Defaults to `[str]`
    """

    plt.rcParams["font.size"] = 64
    base_height = 2
    base_width_per_col = 1.5
    min_width = 3  # minimum total width
    width = max(min_width, base_width_per_col * len(df.columns))
    fig, ax = plt.subplots(figsize=(width, base_height))
    fig.patch.set_facecolor(figure_background_color)
    ax.axis("tight")
    ax.axis("off")

    df_formatted = df.copy()

    if all(isinstance(col, str) for col in money_cols) and len(money_cols) != 0:
        for col in money_cols:
            df_formatted[col] = df_formatted[col].map(
                lambda x: f"{'-' if x < 0 else ''}${abs(x):.2f}"
            )

    # Define cell colors and styles
    def highlight_criteria(cell, value):
        val = value
        if isinstance(cell, str):
            val = cell.replace("$", "")
        if float(val) >= 0:
            return {"color": color_positive}
        else:
            return {"color": color_negative}

    cell_colors = []
    if highlight_column != "" and highlight_column in df_formatted.columns:
        cell_colors = [
            [
                highlight_criteria(cell, value)
                if col == highlight_column
                else {"color": text_color}
                for col, cell in zip(df_formatted.columns, row)
            ]
            for row, value in zip(df_formatted.values, df_formatted[highlight_column])
        ]
    else:
        cell_colors = [
            [{"color": text_color} for _ in row] for row in df_formatted.values
        ]

    df_formatted.columns = df_formatted.columns.str.replace("_", " ").str.title()

    # Create the table
    table = ax.table(
        cellText=df_formatted.values,
        colLabels=df_formatted.columns,
        cellLoc="center",
        loc="center",
    )

    # Set table background and text styles
    for (row, col), cell in table.get_celld().items():
        if row == 0:  # Header row
            cell.set_facecolor(background_color)
            cell.set_text_props(
                color=text_color,
                weight="bold",
            )
        else:  # Data rows
            cell.set_facecolor(background_color)
            custom_style = cell_colors[row - 1][col]
            cell.set_text_props(
                color=custom_style.get("color", text_color),
                fontsize=3 * plt.rcParams["font.size"],
            )

    # Save the image to a BytesIO buffer
    buf = io.BytesIO()
    plt.savefig(
        buf, format="png", bbox_inches="tight", dpi=600, facecolor=fig.get_facecolor()
    )
    buf.seek(0)
    plt.close(fig)
    return buf


# Sample DataFrame Example
if __name__ == "__main__":
    data = {
        "stock_symbol": [
            "PANW",
            "APP",
            "PTC",
            "DDOG",
            "AMD",
            "PCTY",
            "NVDA",
            "BLKB",
            "ENTG",
            "AVGO",
        ],
        "current_price": [
            188.50,
            346.732342,
            185.91,
            147.56,
            125.06434,
            200.604234,
            139.9323,
            76.283235,
            102.23,
            245.3653,
        ],
        "total_gain_loss": [
            -1.01,
            4.90,
            -1.19,
            -0.84,
            -1.23,
            -0.59,
            -0.29,
            0.16,
            -0.62,
            5.68,
        ],
    }

    df = pd.DataFrame(data)

    # Generate and save the image
    image_buffer = dataframe_to_image(
        df, "total_gain_loss", money_cols=["current_price", "total_gain_loss"]
    )
    # Save the BytesIO content to a file
    with open("output_table.png", "wb") as f:
        f.write(image_buffer.getbuffer())
