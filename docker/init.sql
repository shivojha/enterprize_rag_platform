CREATE TABLE IF NOT EXISTS loans (
    id SERIAL PRIMARY KEY,
    loan_id VARCHAR(50) UNIQUE NOT NULL,
    borrower_name VARCHAR(200),
    loan_type VARCHAR(50),
    loan_amount DECIMAL(12,2),
    property_address TEXT,
    stage VARCHAR(100) DEFAULT 'application_submitted',
    status VARCHAR(50) DEFAULT 'active',
    credit_score INT,
    dti_ratio DECIMAL(5,2),
    down_payment_pct DECIMAL(5,2),
    interest_rate DECIMAL(5,3),
    submitted_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    loan_id VARCHAR(50) REFERENCES loans(loan_id),
    doc_type VARCHAR(100),
    file_path TEXT,
    chunk_count INT DEFAULT 0,
    ingested_at TIMESTAMP,
    status VARCHAR(50) DEFAULT 'pending',
    UNIQUE(loan_id, doc_type)
);

CREATE TABLE IF NOT EXISTS query_log (
    id SERIAL PRIMARY KEY,
    loan_id VARCHAR(50),
    question TEXT,
    answer TEXT,
    sources JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ── Demo Loans ────────────────────────────────────────────────────────────────
INSERT INTO loans (loan_id, borrower_name, loan_type, loan_amount, property_address, stage, status, credit_score, dti_ratio, down_payment_pct, interest_rate, submitted_date)
VALUES
  ('LN-2024-001', 'John Smith',    'FHA',          308800.00,   '123 Oak St, Austin TX 78701',         'application_submitted', 'active',   680, 42.30, 3.50,  6.750, '2024-03-01'),
  ('LN-2024-002', 'Maria Garcia',  'Conventional', 432000.00,   '456 Elm Ave, Dallas TX 75201',        'document_review',       'active',   748, 34.70, 20.00, 7.125, '2024-02-15'),
  ('LN-2024-003', 'Robert Johnson','VA',            432437.50,   '789 Pecan Blvd, San Antonio TX 78201','underwriting',          'active',   712, 33.10, 0.00,  6.875, '2024-01-10'),
  ('LN-2024-004', 'Sarah Chen',    'Jumbo',        1480000.00,  '1201 River Oaks Blvd, Houston TX 77019','approved',            'active',   798, 29.20, 20.00, 7.125, '2024-01-20'),
  ('LN-2024-005', 'Michael Brown', 'FHA Refinance', 291250.00,  '567 Birch Lane, Austin TX 78745',     'closing',               'active',   695, 30.20, 0.00,  5.990, '2024-02-28'),
  ('policy',      'FHA Guidelines','Policy',         0.00,       'N/A',                                 'reference',             'active',   NULL, NULL, NULL,  NULL, '2024-01-01')
ON CONFLICT DO NOTHING;
