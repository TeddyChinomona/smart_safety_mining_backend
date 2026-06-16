import numpy as np
from sklearn.tree import DecisionTreeClassifier

# 1. Training data mimicking mining environments
# Feature map: [gas_level, temperature, humidity, heart_rate, fall_detected (0 or 1)]
# Labels: 0 (Safe), 1 (Warning), 2 (Danger)
X_train = np.array([
    [0.1, 22.0, 45.0, 75, 0],   # Normal condition
    [0.5, 25.0, 50.0, 80, 0],   # Normal condition
    [5.0, 30.0, 55.0, 100, 0],  # Warning: Gas building up, HR elevated
    [2.0, 38.0, 60.0, 110, 0],  # Warning: High temperature
    [10.0, 45.0, 65.0, 130, 0], # Danger: Extreme gas, high temp, high HR
    [0.2, 24.0, 45.0, 140, 1],  # Danger: Fall detected, irregular HR
])
y_train = np.array([0, 0, 1, 1, 2, 2])

# 2. Initialize and Train the Decision Tree Classifier
dt_classifier = DecisionTreeClassifier(max_depth=5, random_state=42)
dt_classifier.fit(X_train, y_train)

def predict_risk_level(sensor_event):
    """
    Predicts risk level for a given SensorEvent:
    Returns: 0 (Safe), 1 (Warning), or 2 (Danger)
    """
    gas = sensor_event.gas_level or 0.0
    temp = sensor_event.temperature or 25.0
    humidity = sensor_event.humidity or 50.0
    hr = sensor_event.heart_rate or 80
    fall = 1 if sensor_event.fall_detected else 0

    features = np.array([[gas, temp, humidity, hr, fall]])
    prediction = dt_classifier.predict(features)
    return prediction[0]