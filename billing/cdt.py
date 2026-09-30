"""Common dental procedure (CDT) codes for the invoice pick-list.

The descriptions are short plain-English summaries written for this app, not
the ADA's official CDT descriptors (those are licensed by the ADA). Staff can
type any valid code and their own description; this list only saves typing.
"""

COMMON_CODES = [
    ('D0120', 'Periodic oral exam'),
    ('D0140', 'Limited exam, problem-focused'),
    ('D0150', 'Comprehensive oral exam'),
    ('D0210', 'Full-mouth X-ray series'),
    ('D0220', 'Periapical X-ray, first image'),
    ('D0230', 'Periapical X-ray, each additional'),
    ('D0272', 'Bitewing X-rays, two images'),
    ('D0274', 'Bitewing X-rays, four images'),
    ('D0330', 'Panoramic X-ray'),
    ('D1110', 'Cleaning, adult'),
    ('D1120', 'Cleaning, child'),
    ('D1206', 'Fluoride varnish'),
    ('D1351', 'Sealant, per tooth'),
    ('D2140', 'Amalgam filling, one surface'),
    ('D2150', 'Amalgam filling, two surfaces'),
    ('D2160', 'Amalgam filling, three surfaces'),
    ('D2330', 'Composite filling, front tooth, one surface'),
    ('D2331', 'Composite filling, front tooth, two surfaces'),
    ('D2332', 'Composite filling, front tooth, three surfaces'),
    ('D2391', 'Composite filling, back tooth, one surface'),
    ('D2392', 'Composite filling, back tooth, two surfaces'),
    ('D2393', 'Composite filling, back tooth, three surfaces'),
    ('D2394', 'Composite filling, back tooth, four or more surfaces'),
    ('D2740', 'Crown, porcelain/ceramic'),
    ('D2750', 'Crown, porcelain fused to high noble metal'),
    ('D2751', 'Crown, porcelain fused to base metal'),
    ('D2752', 'Crown, porcelain fused to noble metal'),
    ('D2950', 'Core buildup'),
    ('D2954', 'Prefabricated post and core'),
    ('D3310', 'Root canal, front tooth'),
    ('D3320', 'Root canal, premolar'),
    ('D3330', 'Root canal, molar'),
    ('D4341', 'Scaling and root planing, 4+ teeth per quadrant'),
    ('D4342', 'Scaling and root planing, 1-3 teeth per quadrant'),
    ('D4910', 'Periodontal maintenance'),
    ('D6010', 'Implant placement'),
    ('D7140', 'Extraction, erupted tooth'),
    ('D7210', 'Surgical extraction'),
    ('D9110', 'Emergency treatment for pain'),
    ('D9944', 'Night guard, hard, full arch'),
]
