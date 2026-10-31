# Data

Download the **Brazilian E-Commerce Public Dataset by Olist** from Kaggle
(https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce, CC BY-NC-SA 4.0) and unzip the 9 CSVs
into `data/raw/`. The files are not committed: they're ~125 MB and the license asks for attribution.

For CI and quick local runs, `python scripts/make_sample_data.py` writes a small synthetic dataset with
the same schema to `data/sample/`.
