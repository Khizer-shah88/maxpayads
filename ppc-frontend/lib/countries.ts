export interface Country {
  code: string
  label: string
  flag: string
}

export const COUNTRIES: Country[] = [
  // North America
  { code: 'US', label: 'United States', flag: '\u{1F1FA}\u{1F1F8}' },
  { code: 'CA', label: 'Canada', flag: '\u{1F1E8}\u{1F1E6}' },
  { code: 'MX', label: 'Mexico', flag: '\u{1F1F2}\u{1F1FD}' },
  { code: 'GT', label: 'Guatemala', flag: '\u{1F1EC}\u{1F1F9}' },
  { code: 'CU', label: 'Cuba', flag: '\u{1F1E8}\u{1F1FA}' },
  { code: 'HT', label: 'Haiti', flag: '\u{1F1ED}\u{1F1F9}' },
  { code: 'DO', label: 'Dominican Republic', flag: '\u{1F1E9}\u{1F1F4}' },
  { code: 'HN', label: 'Honduras', flag: '\u{1F1ED}\u{1F1F3}' },
  { code: 'NI', label: 'Nicaragua', flag: '\u{1F1F3}\u{1F1EE}' },
  { code: 'SV', label: 'El Salvador', flag: '\u{1F1F8}\u{1F1FB}' },
  { code: 'CR', label: 'Costa Rica', flag: '\u{1F1E8}\u{1F1F7}' },
  { code: 'PA', label: 'Panama', flag: '\u{1F1F5}\u{1F1E6}' },
  { code: 'JM', label: 'Jamaica', flag: '\u{1F1EF}\u{1F1F2}' },
  { code: 'TT', label: 'Trinidad and Tobago', flag: '\u{1F1F9}\u{1F1F9}' },
  { code: 'BZ', label: 'Belize', flag: '\u{1F1E7}\u{1F1FF}' },
  { code: 'BS', label: 'Bahamas', flag: '\u{1F1E7}\u{1F1F8}' },
  { code: 'BB', label: 'Barbados', flag: '\u{1F1E7}\u{1F1E7}' },
  { code: 'PR', label: 'Puerto Rico', flag: '\u{1F1F5}\u{1F1F7}' },

  // South America
  { code: 'BR', label: 'Brazil', flag: '\u{1F1E7}\u{1F1F7}' },
  { code: 'AR', label: 'Argentina', flag: '\u{1F1E6}\u{1F1F7}' },
  { code: 'CO', label: 'Colombia', flag: '\u{1F1E8}\u{1F1F4}' },
  { code: 'CL', label: 'Chile', flag: '\u{1F1E8}\u{1F1F1}' },
  { code: 'PE', label: 'Peru', flag: '\u{1F1F5}\u{1F1EA}' },
  { code: 'VE', label: 'Venezuela', flag: '\u{1F1FB}\u{1F1EA}' },
  { code: 'EC', label: 'Ecuador', flag: '\u{1F1EA}\u{1F1E8}' },
  { code: 'BO', label: 'Bolivia', flag: '\u{1F1E7}\u{1F1F4}' },
  { code: 'PY', label: 'Paraguay', flag: '\u{1F1F5}\u{1F1FE}' },
  { code: 'UY', label: 'Uruguay', flag: '\u{1F1FA}\u{1F1FE}' },
  { code: 'GY', label: 'Guyana', flag: '\u{1F1EC}\u{1F1FE}' },
  { code: 'SR', label: 'Suriname', flag: '\u{1F1F8}\u{1F1F7}' },

  // Western Europe
  { code: 'GB', label: 'United Kingdom', flag: '\u{1F1EC}\u{1F1E7}' },
  { code: 'DE', label: 'Germany', flag: '\u{1F1E9}\u{1F1EA}' },
  { code: 'FR', label: 'France', flag: '\u{1F1EB}\u{1F1F7}' },
  { code: 'IT', label: 'Italy', flag: '\u{1F1EE}\u{1F1F9}' },
  { code: 'ES', label: 'Spain', flag: '\u{1F1EA}\u{1F1F8}' },
  { code: 'NL', label: 'Netherlands', flag: '\u{1F1F3}\u{1F1F1}' },
  { code: 'BE', label: 'Belgium', flag: '\u{1F1E7}\u{1F1EA}' },
  { code: 'PT', label: 'Portugal', flag: '\u{1F1F5}\u{1F1F9}' },
  { code: 'IE', label: 'Ireland', flag: '\u{1F1EE}\u{1F1EA}' },
  { code: 'AT', label: 'Austria', flag: '\u{1F1E6}\u{1F1F9}' },
  { code: 'CH', label: 'Switzerland', flag: '\u{1F1E8}\u{1F1ED}' },
  { code: 'LU', label: 'Luxembourg', flag: '\u{1F1F1}\u{1F1FA}' },
  { code: 'MC', label: 'Monaco', flag: '\u{1F1F2}\u{1F1E8}' },
  { code: 'LI', label: 'Liechtenstein', flag: '\u{1F1F1}\u{1F1EE}' },
  { code: 'AD', label: 'Andorra', flag: '\u{1F1E6}\u{1F1E9}' },
  { code: 'MT', label: 'Malta', flag: '\u{1F1F2}\u{1F1F9}' },

  // Northern Europe
  { code: 'SE', label: 'Sweden', flag: '\u{1F1F8}\u{1F1EA}' },
  { code: 'NO', label: 'Norway', flag: '\u{1F1F3}\u{1F1F4}' },
  { code: 'DK', label: 'Denmark', flag: '\u{1F1E9}\u{1F1F0}' },
  { code: 'FI', label: 'Finland', flag: '\u{1F1EB}\u{1F1EE}' },
  { code: 'IS', label: 'Iceland', flag: '\u{1F1EE}\u{1F1F8}' },
  { code: 'EE', label: 'Estonia', flag: '\u{1F1EA}\u{1F1EA}' },
  { code: 'LV', label: 'Latvia', flag: '\u{1F1F1}\u{1F1FB}' },
  { code: 'LT', label: 'Lithuania', flag: '\u{1F1F1}\u{1F1F9}' },

  // Eastern Europe
  { code: 'PL', label: 'Poland', flag: '\u{1F1F5}\u{1F1F1}' },
  { code: 'CZ', label: 'Czech Republic', flag: '\u{1F1E8}\u{1F1FF}' },
  { code: 'SK', label: 'Slovakia', flag: '\u{1F1F8}\u{1F1F0}' },
  { code: 'HU', label: 'Hungary', flag: '\u{1F1ED}\u{1F1FA}' },
  { code: 'RO', label: 'Romania', flag: '\u{1F1F7}\u{1F1F4}' },
  { code: 'BG', label: 'Bulgaria', flag: '\u{1F1E7}\u{1F1EC}' },
  { code: 'HR', label: 'Croatia', flag: '\u{1F1ED}\u{1F1F7}' },
  { code: 'RS', label: 'Serbia', flag: '\u{1F1F7}\u{1F1F8}' },
  { code: 'SI', label: 'Slovenia', flag: '\u{1F1F8}\u{1F1EE}' },
  { code: 'BA', label: 'Bosnia and Herzegovina', flag: '\u{1F1E7}\u{1F1E6}' },
  { code: 'ME', label: 'Montenegro', flag: '\u{1F1F2}\u{1F1EA}' },
  { code: 'MK', label: 'North Macedonia', flag: '\u{1F1F2}\u{1F1F0}' },
  { code: 'AL', label: 'Albania', flag: '\u{1F1E6}\u{1F1F1}' },
  { code: 'XK', label: 'Kosovo', flag: '\u{1F1FD}\u{1F1F0}' },
  { code: 'MD', label: 'Moldova', flag: '\u{1F1F2}\u{1F1E9}' },
  { code: 'BY', label: 'Belarus', flag: '\u{1F1E7}\u{1F1FE}' },
  { code: 'UA', label: 'Ukraine', flag: '\u{1F1FA}\u{1F1E6}' },
  { code: 'RU', label: 'Russia', flag: '\u{1F1F7}\u{1F1FA}' },
  { code: 'GE', label: 'Georgia', flag: '\u{1F1EC}\u{1F1EA}' },
  { code: 'AM', label: 'Armenia', flag: '\u{1F1E6}\u{1F1F2}' },
  { code: 'AZ', label: 'Azerbaijan', flag: '\u{1F1E6}\u{1F1FF}' },

  // Southern Europe
  { code: 'GR', label: 'Greece', flag: '\u{1F1EC}\u{1F1F7}' },
  { code: 'CY', label: 'Cyprus', flag: '\u{1F1E8}\u{1F1FE}' },
  { code: 'TR', label: 'Turkey', flag: '\u{1F1F9}\u{1F1F7}' },

  // Middle East
  { code: 'SA', label: 'Saudi Arabia', flag: '\u{1F1F8}\u{1F1E6}' },
  { code: 'AE', label: 'UAE', flag: '\u{1F1E6}\u{1F1EA}' },
  { code: 'QA', label: 'Qatar', flag: '\u{1F1F6}\u{1F1E6}' },
  { code: 'KW', label: 'Kuwait', flag: '\u{1F1F0}\u{1F1FC}' },
  { code: 'BH', label: 'Bahrain', flag: '\u{1F1E7}\u{1F1ED}' },
  { code: 'OM', label: 'Oman', flag: '\u{1F1F4}\u{1F1F2}' },
  { code: 'YE', label: 'Yemen', flag: '\u{1F1FE}\u{1F1EA}' },
  { code: 'JO', label: 'Jordan', flag: '\u{1F1EF}\u{1F1F4}' },
  { code: 'LB', label: 'Lebanon', flag: '\u{1F1F1}\u{1F1E7}' },
  { code: 'IQ', label: 'Iraq', flag: '\u{1F1EE}\u{1F1F6}' },
  { code: 'IR', label: 'Iran', flag: '\u{1F1EE}\u{1F1F7}' },
  { code: 'SY', label: 'Syria', flag: '\u{1F1F8}\u{1F1FE}' },
  { code: 'PS', label: 'Palestine', flag: '\u{1F1F5}\u{1F1F8}' },
  { code: 'IL', label: 'Israel', flag: '\u{1F1EE}\u{1F1F1}' },

  // Central Asia
  { code: 'KZ', label: 'Kazakhstan', flag: '\u{1F1F0}\u{1F1FF}' },
  { code: 'UZ', label: 'Uzbekistan', flag: '\u{1F1FA}\u{1F1FF}' },
  { code: 'TM', label: 'Turkmenistan', flag: '\u{1F1F9}\u{1F1F2}' },
  { code: 'TJ', label: 'Tajikistan', flag: '\u{1F1F9}\u{1F1EF}' },
  { code: 'KG', label: 'Kyrgyzstan', flag: '\u{1F1F0}\u{1F1EC}' },
  { code: 'AF', label: 'Afghanistan', flag: '\u{1F1E6}\u{1F1EB}' },
  { code: 'MN', label: 'Mongolia', flag: '\u{1F1F2}\u{1F1F3}' },

  // South Asia
  { code: 'IN', label: 'India', flag: '\u{1F1EE}\u{1F1F3}' },
  { code: 'PK', label: 'Pakistan', flag: '\u{1F1F5}\u{1F1F0}' },
  { code: 'BD', label: 'Bangladesh', flag: '\u{1F1E7}\u{1F1E9}' },
  { code: 'LK', label: 'Sri Lanka', flag: '\u{1F1F1}\u{1F1F0}' },
  { code: 'NP', label: 'Nepal', flag: '\u{1F1F3}\u{1F1F5}' },
  { code: 'BT', label: 'Bhutan', flag: '\u{1F1E7}\u{1F1F9}' },
  { code: 'MV', label: 'Maldives', flag: '\u{1F1F2}\u{1F1FB}' },

  // East Asia
  { code: 'CN', label: 'China', flag: '\u{1F1E8}\u{1F1F3}' },
  { code: 'JP', label: 'Japan', flag: '\u{1F1EF}\u{1F1F5}' },
  { code: 'KR', label: 'South Korea', flag: '\u{1F1F0}\u{1F1F7}' },
  { code: 'KP', label: 'North Korea', flag: '\u{1F1F0}\u{1F1F5}' },
  { code: 'TW', label: 'Taiwan', flag: '\u{1F1F9}\u{1F1FC}' },
  { code: 'HK', label: 'Hong Kong', flag: '\u{1F1ED}\u{1F1F0}' },
  { code: 'MO', label: 'Macau', flag: '\u{1F1F2}\u{1F1F4}' },

  // Southeast Asia
  { code: 'ID', label: 'Indonesia', flag: '\u{1F1EE}\u{1F1E9}' },
  { code: 'MY', label: 'Malaysia', flag: '\u{1F1F2}\u{1F1FE}' },
  { code: 'TH', label: 'Thailand', flag: '\u{1F1F9}\u{1F1ED}' },
  { code: 'VN', label: 'Vietnam', flag: '\u{1F1FB}\u{1F1F3}' },
  { code: 'PH', label: 'Philippines', flag: '\u{1F1F5}\u{1F1ED}' },
  { code: 'SG', label: 'Singapore', flag: '\u{1F1F8}\u{1F1EC}' },
  { code: 'MM', label: 'Myanmar', flag: '\u{1F1F2}\u{1F1F2}' },
  { code: 'KH', label: 'Cambodia', flag: '\u{1F1F0}\u{1F1ED}' },
  { code: 'LA', label: 'Laos', flag: '\u{1F1F1}\u{1F1E6}' },
  { code: 'BN', label: 'Brunei', flag: '\u{1F1E7}\u{1F1F3}' },
  { code: 'TL', label: 'Timor-Leste', flag: '\u{1F1F9}\u{1F1F1}' },

  // Oceania
  { code: 'AU', label: 'Australia', flag: '\u{1F1E6}\u{1F1FA}' },
  { code: 'NZ', label: 'New Zealand', flag: '\u{1F1F3}\u{1F1FF}' },
  { code: 'FJ', label: 'Fiji', flag: '\u{1F1EB}\u{1F1EF}' },
  { code: 'PG', label: 'Papua New Guinea', flag: '\u{1F1F5}\u{1F1EC}' },
  { code: 'WS', label: 'Samoa', flag: '\u{1F1FC}\u{1F1F8}' },
  { code: 'TO', label: 'Tonga', flag: '\u{1F1F9}\u{1F1F4}' },
  { code: 'VU', label: 'Vanuatu', flag: '\u{1F1FB}\u{1F1FA}' },

  // North Africa
  { code: 'EG', label: 'Egypt', flag: '\u{1F1EA}\u{1F1EC}' },
  { code: 'MA', label: 'Morocco', flag: '\u{1F1F2}\u{1F1E6}' },
  { code: 'DZ', label: 'Algeria', flag: '\u{1F1E9}\u{1F1FF}' },
  { code: 'TN', label: 'Tunisia', flag: '\u{1F1F9}\u{1F1F3}' },
  { code: 'LY', label: 'Libya', flag: '\u{1F1F1}\u{1F1FE}' },
  { code: 'SD', label: 'Sudan', flag: '\u{1F1F8}\u{1F1E9}' },

  // West Africa
  { code: 'NG', label: 'Nigeria', flag: '\u{1F1F3}\u{1F1EC}' },
  { code: 'GH', label: 'Ghana', flag: '\u{1F1EC}\u{1F1ED}' },
  { code: 'CI', label: 'Ivory Coast', flag: '\u{1F1E8}\u{1F1EE}' },
  { code: 'SN', label: 'Senegal', flag: '\u{1F1F8}\u{1F1F3}' },
  { code: 'ML', label: 'Mali', flag: '\u{1F1F2}\u{1F1F1}' },
  { code: 'BF', label: 'Burkina Faso', flag: '\u{1F1E7}\u{1F1EB}' },
  { code: 'NE', label: 'Niger', flag: '\u{1F1F3}\u{1F1EA}' },
  { code: 'GN', label: 'Guinea', flag: '\u{1F1EC}\u{1F1F3}' },
  { code: 'SL', label: 'Sierra Leone', flag: '\u{1F1F8}\u{1F1F1}' },
  { code: 'LR', label: 'Liberia', flag: '\u{1F1F1}\u{1F1F7}' },
  { code: 'TG', label: 'Togo', flag: '\u{1F1F9}\u{1F1EC}' },
  { code: 'BJ', label: 'Benin', flag: '\u{1F1E7}\u{1F1EF}' },
  { code: 'MR', label: 'Mauritania', flag: '\u{1F1F2}\u{1F1F7}' },
  { code: 'GM', label: 'Gambia', flag: '\u{1F1EC}\u{1F1F2}' },
  { code: 'GW', label: 'Guinea-Bissau', flag: '\u{1F1EC}\u{1F1FC}' },
  { code: 'CV', label: 'Cape Verde', flag: '\u{1F1E8}\u{1F1FB}' },

  // East Africa
  { code: 'KE', label: 'Kenya', flag: '\u{1F1F0}\u{1F1EA}' },
  { code: 'ET', label: 'Ethiopia', flag: '\u{1F1EA}\u{1F1F9}' },
  { code: 'TZ', label: 'Tanzania', flag: '\u{1F1F9}\u{1F1FF}' },
  { code: 'UG', label: 'Uganda', flag: '\u{1F1FA}\u{1F1EC}' },
  { code: 'RW', label: 'Rwanda', flag: '\u{1F1F7}\u{1F1FC}' },
  { code: 'BI', label: 'Burundi', flag: '\u{1F1E7}\u{1F1EE}' },
  { code: 'SO', label: 'Somalia', flag: '\u{1F1F8}\u{1F1F4}' },
  { code: 'DJ', label: 'Djibouti', flag: '\u{1F1E9}\u{1F1EF}' },
  { code: 'ER', label: 'Eritrea', flag: '\u{1F1EA}\u{1F1F7}' },
  { code: 'SS', label: 'South Sudan', flag: '\u{1F1F8}\u{1F1F8}' },
  { code: 'MG', label: 'Madagascar', flag: '\u{1F1F2}\u{1F1EC}' },
  { code: 'MU', label: 'Mauritius', flag: '\u{1F1F2}\u{1F1FA}' },
  { code: 'SC', label: 'Seychelles', flag: '\u{1F1F8}\u{1F1E8}' },

  // Central Africa
  { code: 'CD', label: 'DR Congo', flag: '\u{1F1E8}\u{1F1E9}' },
  { code: 'CG', label: 'Congo', flag: '\u{1F1E8}\u{1F1EC}' },
  { code: 'CM', label: 'Cameroon', flag: '\u{1F1E8}\u{1F1F2}' },
  { code: 'AO', label: 'Angola', flag: '\u{1F1E6}\u{1F1F4}' },
  { code: 'GA', label: 'Gabon', flag: '\u{1F1EC}\u{1F1E6}' },
  { code: 'GQ', label: 'Equatorial Guinea', flag: '\u{1F1EC}\u{1F1F6}' },
  { code: 'CF', label: 'Central African Republic', flag: '\u{1F1E8}\u{1F1EB}' },
  { code: 'TD', label: 'Chad', flag: '\u{1F1F9}\u{1F1E9}' },

  // Southern Africa
  { code: 'ZA', label: 'South Africa', flag: '\u{1F1FF}\u{1F1E6}' },
  { code: 'ZW', label: 'Zimbabwe', flag: '\u{1F1FF}\u{1F1FC}' },
  { code: 'ZM', label: 'Zambia', flag: '\u{1F1FF}\u{1F1F2}' },
  { code: 'MW', label: 'Malawi', flag: '\u{1F1F2}\u{1F1FC}' },
  { code: 'MZ', label: 'Mozambique', flag: '\u{1F1F2}\u{1F1FF}' },
  { code: 'BW', label: 'Botswana', flag: '\u{1F1E7}\u{1F1FC}' },
  { code: 'NA', label: 'Namibia', flag: '\u{1F1F3}\u{1F1E6}' },
  { code: 'SZ', label: 'Eswatini', flag: '\u{1F1F8}\u{1F1FF}' },
  { code: 'LS', label: 'Lesotho', flag: '\u{1F1F1}\u{1F1F8}' },
]

// Build a code->name lookup from the COUNTRIES array
export const COUNTRY_NAMES: Record<string, string> = Object.fromEntries(
  COUNTRIES.map(c => [c.code, c.label])
)
