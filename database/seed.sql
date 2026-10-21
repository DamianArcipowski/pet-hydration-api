CREATE DATABASE pet_hydration;
USE pet_hydration;

CREATE TABLE users (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    email       VARCHAR(255) NOT NULL UNIQUE,
    password    VARCHAR(255) NOT NULL
);

CREATE TABLE devices (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    mac_address       VARCHAR(17) NOT NULL UNIQUE,
    user_id           INT NOT NULL,
    name              VARCHAR(50),
    pending_command   ENUM('tare') NULL DEFAULT NULL,
    calibration       FLOAT NULL DEFAULT NULL,
    bowl_weight_g     FLOAT NOT NULL DEFAULT 0, 
    bowl_capacity_ml  INT NOT NULL DEFAULT 0,
    fill_low_pct      FLOAT DEFAULT 0.20,
    fill_target_pct   FLOAT DEFAULT 0.80,
    wifi_ssid         VARCHAR(80),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE pets (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    device_id   INT NOT NULL UNIQUE,
    name        VARCHAR(50) NOT NULL,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
);

CREATE TABLE pet_weight_log (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    pet_id      INT NOT NULL,
    weight_kg   FLOAT NOT NULL,
    measured_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (pet_id) REFERENCES pets(id) ON DELETE CASCADE
);

CREATE TABLE readings (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    device_id   INT NOT NULL,
    weight_g    FLOAT NOT NULL,
    valve_open  TINYINT(1) DEFAULT 0,
    tank_low    TINYINT(1) DEFAULT 0,
    calibrated  TINYINT(1) DEFAULT 0,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
);

CREATE TABLE daily_summaries (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    device_id       INT NOT NULL,
    date            DATE NOT NULL,
    total_ml        INT NOT NULL,
    valve_opens     INT DEFAULT 0,
    valve_open_s    INT DEFAULT 0,
    avg_weight_g    FLOAT,
    UNIQUE KEY uq_device_date (device_id, date),
    FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
);

CREATE TABLE pending_devices (
    mac_address VARCHAR(17) PRIMARY KEY,
    first_seen  DATETIME DEFAULT CURRENT_TIMESTAMP
);
