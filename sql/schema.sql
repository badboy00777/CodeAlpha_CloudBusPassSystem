CREATE DATABASE IF NOT EXISTS buspass CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE buspass;

CREATE TABLE IF NOT EXISTS users (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  full_name VARCHAR(80) NOT NULL,
  email VARCHAR(120) NOT NULL UNIQUE,
  password_hash VARCHAR(100) NOT NULL,
  phone_enc VARBINARY(200) NULL,
  role ENUM('passenger','conductor') NOT NULL DEFAULT 'passenger',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS routes (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(10) NOT NULL UNIQUE,
  origin VARCHAR(60) NOT NULL,
  destination VARCHAR(60) NOT NULL,
  daily_capacity INT UNSIGNED NOT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS fares (
  id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  route_id INT UNSIGNED NOT NULL,
  pass_type ENUM('daily','weekly','monthly') NOT NULL,
  duration_days SMALLINT UNSIGNED NOT NULL,
  price_pkr INT UNSIGNED NOT NULL,
  UNIQUE KEY uq_route_pass (route_id, pass_type),
  FOREIGN KEY (route_id) REFERENCES routes(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS concessions (
  code VARCHAR(20) PRIMARY KEY,
  percent_off TINYINT UNSIGNED NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS route_capacity (
  route_id INT UNSIGNED NOT NULL,
  travel_date DATE NOT NULL,
  sold INT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (route_id, travel_date),
  FOREIGN KEY (route_id) REFERENCES routes(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS bookings (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id INT UNSIGNED NOT NULL,
  route_id INT UNSIGNED NOT NULL,
  pass_type ENUM('daily','weekly','monthly') NOT NULL,
  concession_code VARCHAR(20) NOT NULL,
  travel_date DATE NOT NULL,
  valid_until DATE NOT NULL,
  price_pkr INT UNSIGNED NOT NULL,
  idempotency_key VARCHAR(64) NOT NULL,
  ticket_code VARCHAR(200) NULL,
  status ENUM('active','used','cancelled') NOT NULL DEFAULT 'active',
  used_at DATETIME NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_user_key (user_id, idempotency_key),
  KEY idx_user (user_id),
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (route_id) REFERENCES routes(id),
  FOREIGN KEY (concession_code) REFERENCES concessions(code)
) ENGINE=InnoDB;

INSERT IGNORE INTO concessions (code, percent_off) VALUES ('none', 0), ('student', 50), ('senior', 30);

INSERT IGNORE INTO routes (code, origin, destination, daily_capacity) VALUES
  ('KHI-01', 'Saddar', 'Korangi', 40),
  ('KHI-02', 'Gulshan-e-Iqbal', 'Clifton', 40),
  ('KHI-03', 'Nazimabad', 'Malir', 40);

INSERT IGNORE INTO fares (route_id, pass_type, duration_days, price_pkr) VALUES
  ((SELECT id FROM routes WHERE code='KHI-01'), 'daily', 1, 150),
  ((SELECT id FROM routes WHERE code='KHI-01'), 'weekly', 7, 800),
  ((SELECT id FROM routes WHERE code='KHI-01'), 'monthly', 30, 2800),
  ((SELECT id FROM routes WHERE code='KHI-02'), 'daily', 1, 200),
  ((SELECT id FROM routes WHERE code='KHI-02'), 'weekly', 7, 1000),
  ((SELECT id FROM routes WHERE code='KHI-02'), 'monthly', 30, 3500),
  ((SELECT id FROM routes WHERE code='KHI-03'), 'daily', 1, 120),
  ((SELECT id FROM routes WHERE code='KHI-03'), 'weekly', 7, 650),
  ((SELECT id FROM routes WHERE code='KHI-03'), 'monthly', 30, 2200);