import numpy as np
from sklearn.linear_model import LogisticRegression
import pickle


def train_model():
    """Обучает простую модель на синтетических данных."""
    np.random.seed(42)
    # Признаки: [is_verified_seller, images_qty, description_length, category]
    X = np.random.rand(1000, 4)
    # Целевая переменная: 1 = нарушение, 0 = нет нарушения
    y = (X[:, 0] < 0.3) & (X[:, 1] < 0.2)
    y = y.astype(int)

    model = LogisticRegression()
    model.fit(X, y)
    return model


def save_model(model, path="model.pkl"):
    with open(path, "wb") as f:
        pickle.dump(model, f)


def load_model(path="model.pkl"):
    with open(path, "rb") as f:
        return pickle.load(f)
