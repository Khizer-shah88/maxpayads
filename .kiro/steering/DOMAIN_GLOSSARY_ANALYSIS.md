# Domain Glossary Analysis & Standardization Report

## Executive Summary

This document analyzes the current PPC system against the required Domain Glossary and identifies gaps, inconsistencies, and required standardizations.

## Required Domain Glossary (Source of Truth)

| Term | Definition |
|------|------------|
| **Publisher** | Entity that sends visitors to the network. Has a permanent Publisher ID. |
| **Registered Publisher** | Signs up via the existing PUB panel; approved by Admin. |
| **Manual Publisher** | Created directly by Admin; no login, no website. |
| **Website/Site** | Belongs to a registered publisher; distinguishes traffic from different sites of the same publisher. |
| **Smartlink** | The entry URL given to a publisher. |
| **Domain** | A hostname used in the redirect chain: Anchor, Inter, or Prelander type. |
| **Anchor** | First redirect domain that receives the Smartlink. |
| **Inter** | Intermediate redirect domain after Anchor. |
| **Prelander** | Optional page shown before the final offer. |
| **Prelander Pool** | The single main pool of prelander domains, grouped by OS, with weighted distribution. |
| **Chain** | Admin-configured pairing of Anchor + Inter + Prelander Pool + status. |
| **Campaign** | Stores destination URL(s) and OS/country-specific values + Password/text + Skip Prelander + Remove Referrer flags. |
| **Offer** | Eligibility rule: which campaign is allowed for which publisher(s)/website(s)/country/OS. |
| **OS** | Windows, Android/APK, Mac, iOS — use the existing fixed OS enum already in the system, do not invent new OS values. |
| **CPC** | Cost Per Click — fixed monetary amount (not %) credited per valid click. |
| **Impression (Direct Link Stats)** | ALL clicks (valid + invalid) within the OS scope selected for that report. |
| **Valid click** | A click qualified as valid by the existing fraud/tracking logic. |
| **Conversion** | Manually entered by Admin, per date, for Direct Link Stats. |
| **Weight** | Relative (not %) number controlling prelander traffic distribution. |

---

## Current System State Analysis

### ✅ CORRECTLY IMPLEMENTED

1. **Publisher Model** (`app/models/publisher.py`)
   - ✅ Correctly distinguishes `is_admin_created` flag
   - ✅ Has `public_id` field (e.g., "PUB_ABC12XYZ")
   - ✅ Status field: "pending", "active", "suspended"

2. **Website Model** (`app/models/website.py`)
   - ✅ Correctly belongs to a publisher via `publisher_id`
   - ✅ Has `public_id` field (e.g., "SITE_XYZ789AB")
   - ✅ Tracks clicks and earnings per site

3. **Smartlink Service** (`app/services/smartlink_service.py`)
   - ✅ Correctly generates entry URLs for publishers
   - ✅ Supports public IDs (PUB_XXX, SITE_XXX)
   - ✅ Configurable parameters

4. **Campaign Model** (`app/models/campaign.py`)
   - ✅ Stores destination URL (`default_offer_url`)
   - ✅ Has `password` field
   - ✅ Has `direct_redirect_mode` (Skip Prelander flag)
   - ✅ Has `referrer_suppression` (Remove Referrer flag)
   - ✅ Has `device_os` field for OS-specific campaigns

5. **Offer Schema** (`app/schemas/offer_schema.py`)
   - ✅ Correctly defines eligibility rules
   - ✅ Has `publisher_ids`, `website_ids`, `os_types`, `country_codes`
   - ✅ Links to campaign via `campaign_id`

6. **Redirect Chain Model** (`app/models/redirect_chain.py`)
   - ✅ Has `anchor_domain`, `intermediate_domain`, `pre_lander_pool`
   - ✅ Has status field
   - ✅ Tracks sessions and conversions

---

### ⚠️ INCONSISTENCIES FOUND

#### 1. **Domain Type Terminology**

**Current Implementation:**
```python
# app/schemas/redirection_domain_schema.py
DomainType = Literal["link", "intermediate", "last"]
```

**Required Terminology:**
- "link" → Should be **"anchor"**
- "intermediate" → Should be **"inter"**
- "last" → Should be **"prelander"**

**Impact:** HIGH
- Affects database schema
- Affects all domain resolution logic
- Affects frontend UI labels
- Must maintain backward compatibility during migration

**Files Affected:**
- `app/schemas/redirection_domain_schema.py`
- `app/services/domain_service.py`
- `app/routers/redirection_domain_router.py`
- `app/routers/redirect_chain_router.py`
- `app/services/prelander_service.py`
- `app/middleware/redirect_chain_middleware.py`
- Database indexes in `app/database.py`
- Frontend: `app/admin/redirection-domains/page.tsx`

---

#### 2. **OS Enum Definition**

**Current Implementation:**
```python
# app/schemas/offer_schema.py
_ALLOWED_OS = frozenset({"windows", "mac", "android"})

# app/schemas/prelander_template_schema.py
TemplateOs = Literal["windows", "mac", "both"]

# In traffic_router.py
os_param = "mac" if (os_name or "").lower() in ("mac os", "mac os x", "macos", "ios") else "windows"
```

**Required Terminology:**
- Windows ✅
- Android/APK ❌ (currently just "android")
- Mac ✅
- iOS ❌ (currently not in enum, treated as "mac")

**Issues:**
1. iOS is not a distinct OS in the enum, but the glossary requires it
2. "android" vs "Android/APK" naming inconsistency
3. Prelander templates use "both" instead of allowing multiple OS selection
4. Traffic router treats iOS as Mac (incorrect per glossary)

**Impact:** MEDIUM
- Affects OS detection logic
- Affects prelander template assignment
- Affects offer targeting
- Affects statistics breakdown

**Files Affected:**
- `app/schemas/offer_schema.py`
- `app/schemas/prelander_template_schema.py`
- `app/services/traffic_router.py`
- `app/models/campaign.py`
- `app/utils/device_detection.py` (if exists)

---

#### 3. **Prelander Pool Terminology**

**Current Implementation:**
```python
# app/models/redirect_chain.py
pre_lander_pool: List[str] = Field(default_factory=list)
```

**Required Terminology:**
- Should be **"prelander_pool"** (no underscore)
- Should support OS grouping
- Should support weighted distribution

**Issues:**
1. Field name has underscore: `pre_lander_pool` vs required `prelander_pool`
2. No OS grouping support
3. No weighted distribution support

**Impact:** MEDIUM
- Database field name migration
- OS-based prelander selection logic
- Weighted rotation logic

**Files Affected:**
- `app/models/redirect_chain.py`
- `app/services/prelander_service.py`
- `app/routers/redirect_chain_router.py`

---

#### 4. **Missing OS Enum in Constants**

**Current Implementation:**
```python
# app/core/constants.py
# No OS enum defined
```

**Required:**
- Centralized OS enum in constants.py
- Should be: `("windows", "android", "mac", "ios")`

**Impact:** LOW
- Standardization issue
- Risk of hard-coding OS values in multiple places

**Files Affected:**
- `app/core/constants.py`
- All files that reference OS values

---

#### 5. **CPC Terminology**

**Current Implementation:**
```python
# app/models/publisher.py
custom_cpc: Optional[float] = None

# In offer_schema.py
payout: float = Field(default=0.0, ge=0)
```

**Required Terminology:**
- Should be **"cpc"** not "payout"
- Should be fixed monetary amount (not percentage)

**Issues:**
1. Offer uses "payout" instead of "cpc"
2. Both terms exist (inconsistent)

**Impact:** LOW
- Naming consistency
- User-facing labels

**Files Affected:**
- `app/schemas/offer_schema.py`
- `app/models/publisher.py`
- Frontend labels

---

## Migration Strategy

### Phase 1: Add New Terminology (Non-Breaking)
1. Add new OS enum to `constants.py`
2. Add domain type aliases (maintain old ones for backward compatibility)
3. Add database field aliases

### Phase 2: Update Business Logic
1. Update domain resolution to use new terminology
2. Update OS detection to support iOS
3. Update prelander pool to support OS grouping and weights
4. Update traffic router to use new domain types

### Phase 3: Update Frontend
1. Update UI labels to use correct terminology
2. Add OS grouping UI for prelander pools
3. Add weight distribution UI

### Phase 4: Database Migration
1. Create migration scripts
2. Run data migration
3. Update indexes

### Phase 5: Deprecation
1. Remove old terminology aliases
2. Clean up backward compatibility code

---

## Immediate Actions Required

### Priority 1: Domain Type Renaming
- [ ] Update `DomainType` literal to use correct terminology
- [ ] Add backward compatibility layer
- [ ] Update all domain resolution functions
- [ ] Test redirect flow thoroughly

### Priority 2: OS Enum Standardization
- [ ] Add centralized OS enum to `constants.py`
- [ ] Update all OS references to use enum
- [ ] Fix iOS detection and treatment
- [ ] Update prelander template OS handling

### Priority 3: Prelander Pool Enhancement
- [ ] Rename field to `prelander_pool`
- [ ] Add OS grouping support
- [ ] Add weight distribution logic
- [ ] Update chain creation/update logic

### Priority 4: Terminology Cleanup
- [ ] Replace "payout" with "cpc" in offers
- [ ] Update all user-facing labels
- [ ] Update documentation
- [ ] Update API response fields

---

## Risk Assessment

### High Risk
- Domain type renaming (affects redirect flow)
- OS enum changes (affects targeting logic)

### Medium Risk
- Prelander pool field rename
- CPC terminology change

### Low Risk
- UI label updates
- Documentation updates

---

## Testing Requirements

After each phase:
1. Run all existing tests (must pass)
2. Test redirect flow (Anchor → Inter → Prelander → Offer)
3. Test OS detection for all 4 OS types
4. Test prelander pool weighted distribution
5. Test backward compatibility with old data
6. Performance test with large datasets

---

## Conclusion

The system is largely well-structured but has terminology inconsistencies that must be resolved. The most critical issue is the domain type naming (`link`/`intermediate`/`last` vs `anchor`/`inter`/`prelander`), which affects the core redirect flow.

**Recommendation:** Implement changes in phases with extensive testing at each stage to ensure no regression in working functionality.
