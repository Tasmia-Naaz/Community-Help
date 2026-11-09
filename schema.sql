-- =====================================================================
-- COMMUNITY HELP CONNECT - DATABASE SCHEMA (MySQL 8.0+)
-- Description: Centralized community-support coordination database schema
-- Encoding: UTF8MB4 for full internationalization and emoji support
-- =====================================================================

CREATE DATABASE IF NOT EXISTS `community_help_db` 
  DEFAULT CHARACTER SET utf8mb4 
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE `community_help_db`;

-- Drop existing tables in reverse dependency order
SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS `resource_requests`;
DROP TABLE IF EXISTS `status_history`;
DROP TABLE IF EXISTS `emergency_events`;
DROP TABLE IF EXISTS `notifications`;
DROP TABLE IF EXISTS `resource_listings`;
DROP TABLE IF EXISTS `help_requests`;
DROP TABLE IF EXISTS `users`;
SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------
-- 1. USERS TABLE
-- ---------------------------------------------------------------------
CREATE TABLE `users` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `full_name` VARCHAR(120) NOT NULL,
  `email` VARCHAR(120) NOT NULL UNIQUE,
  `phone` VARCHAR(30) NOT NULL,
  `password_hash` VARCHAR(255) NOT NULL,
  `locality` VARCHAR(100) NOT NULL,
  `role` ENUM('help_seeker', 'volunteer', 'donor', 'admin') NOT NULL DEFAULT 'help_seeker',
  `is_verified` BOOLEAN NOT NULL DEFAULT TRUE,
  `is_suspended` BOOLEAN NOT NULL DEFAULT FALSE,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX `idx_users_role` (`role`),
  INDEX `idx_users_locality` (`locality`),
  INDEX `idx_users_email` (`email`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 2. HELP REQUESTS TABLE
-- ---------------------------------------------------------------------
CREATE TABLE `help_requests` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `seeker_id` INT NOT NULL,
  `category` VARCHAR(60) NOT NULL,
  `title` VARCHAR(150) NOT NULL,
  `description` TEXT NOT NULL,
  `urgency` ENUM('Normal', 'Urgent', 'Critical') NOT NULL DEFAULT 'Normal',
  `locality` VARCHAR(100) NOT NULL,
  `deadline` DATETIME NULL,
  `contact_preference` ENUM('share_always', 'share_on_accept', 'hide_private') NOT NULL DEFAULT 'share_on_accept',
  `status` ENUM('Pending', 'Accepted', 'In Progress', 'awaiting_confirmation', 'disputed', 'Completed', 'Cancelled') NOT NULL DEFAULT 'Pending',
  `assigned_volunteer_id` INT NULL,
  `volunteer_completed_at` TIMESTAMP NULL,
  `completion_note` TEXT NULL,
  `seeker_confirmed_at` TIMESTAMP NULL,
  `confirmed_by_id` INT NULL,
  `dispute_reason` TEXT NULL,
  `disputed_at` TIMESTAMP NULL,
  `rating` INT NULL,
  `feedback` TEXT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT `fk_requests_seeker` FOREIGN KEY (`seeker_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_requests_volunteer` FOREIGN KEY (`assigned_volunteer_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  CONSTRAINT `fk_requests_confirmed_by` FOREIGN KEY (`confirmed_by_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  INDEX `idx_requests_status` (`status`),
  INDEX `idx_requests_urgency` (`urgency`),
  INDEX `idx_requests_locality` (`locality`),
  INDEX `idx_requests_category` (`category`),
  INDEX `idx_requests_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 3. RESOURCE LISTINGS TABLE
-- ---------------------------------------------------------------------
CREATE TABLE `resource_listings` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `donor_id` INT NOT NULL,
  `category` VARCHAR(60) NOT NULL,
  `name` VARCHAR(150) NULL,
  `description` TEXT NOT NULL,
  `quantity` DECIMAL(10, 2) NOT NULL DEFAULT 1.00,
  `unit` VARCHAR(30) NOT NULL DEFAULT 'units',
  `locality` VARCHAR(100) NOT NULL,
  `available_until` DATETIME NULL,
  `expiry_date` DATETIME NULL,
  `pickup_instructions` TEXT NULL,
  `contact_preference` ENUM('share_always', 'share_on_accept', 'hide_private') NOT NULL DEFAULT 'share_always',
  `status` ENUM('Available', 'Reserved', 'Collected', 'Distributed', 'Withdrawn') NOT NULL DEFAULT 'Available',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT `fk_resources_donor` FOREIGN KEY (`donor_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  INDEX `idx_resources_status` (`status`),
  INDEX `idx_resources_locality` (`locality`),
  INDEX `idx_resources_category` (`category`),
  INDEX `idx_resources_expiry` (`expiry_date`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 4. NOTIFICATIONS TABLE
-- ---------------------------------------------------------------------
CREATE TABLE `notifications` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `user_id` INT NOT NULL,
  `title` VARCHAR(120) NOT NULL,
  `message` TEXT NOT NULL,
  `link` VARCHAR(255) NULL,
  `is_read` BOOLEAN NOT NULL DEFAULT FALSE,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT `fk_notifications_user` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  INDEX `idx_notifications_user_read` (`user_id`, `is_read`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 5. EMERGENCY EVENTS TABLE
-- ---------------------------------------------------------------------
CREATE TABLE `emergency_events` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `created_by_id` INT NULL,
  `emergency_type` VARCHAR(100) NOT NULL,
  `affected_locality` VARCHAR(100) NOT NULL,
  `severity` ENUM('Low', 'Moderate', 'Severe', 'Catastrophic') NOT NULL DEFAULT 'Severe',
  `description` TEXT NOT NULL,
  `is_active` BOOLEAN NOT NULL DEFAULT TRUE,
  `activated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `deactivated_at` DATETIME NULL,
  CONSTRAINT `fk_emergency_creator` FOREIGN KEY (`created_by_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  INDEX `idx_emergency_active` (`is_active`),
  INDEX `idx_emergency_locality` (`affected_locality`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 6. STATUS HISTORY AUDIT LOG TABLE
-- ---------------------------------------------------------------------
CREATE TABLE `status_history` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `entity_type` VARCHAR(30) NOT NULL,
  `entity_id` INT NOT NULL,
  `previous_status` VARCHAR(30) NOT NULL,
  `new_status` VARCHAR(30) NOT NULL,
  `changed_by_id` INT NULL,
  `notes` TEXT NULL,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT `fk_status_changed_by` FOREIGN KEY (`changed_by_id`) REFERENCES `users` (`id`) ON DELETE SET NULL,
  INDEX `idx_history_entity` (`entity_type`, `entity_id`),
  INDEX `idx_history_created_at` (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------
-- 7. VOLUNTEER REQUESTS FOR EXISTING DONOR RESOURCE LISTINGS
-- ---------------------------------------------------------------------
CREATE TABLE `resource_requests` (
  `id` INT AUTO_INCREMENT PRIMARY KEY,
  `resource_id` INT NOT NULL,
  `volunteer_id` INT NOT NULL,
  `quantity` DECIMAL(10, 2) NOT NULL,
  `status` VARCHAR(20) NOT NULL DEFAULT 'Pending',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT `fk_resource_requests_listing` FOREIGN KEY (`resource_id`) REFERENCES `resource_listings` (`id`) ON DELETE CASCADE,
  CONSTRAINT `fk_resource_requests_volunteer` FOREIGN KEY (`volunteer_id`) REFERENCES `users` (`id`) ON DELETE CASCADE,
  INDEX `idx_resource_requests_resource_status` (`resource_id`, `status`),
  INDEX `idx_resource_requests_volunteer_status` (`volunteer_id`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
