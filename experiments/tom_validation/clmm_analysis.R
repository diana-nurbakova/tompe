#!/usr/bin/env Rscript
# §5.4 — Cumulative Link Mixed Model (CLMM) for V3.
#
# Fits an ordinal regression on detection_count (1, 2, 3) with:
#   Fixed effects: tom_level (linear), severity, segment_length, system_quality
#   Random effects: (1 | system) + (1 | doc)
#   (rater_triplet random effect omitted — too many unique triplets to identify)
#
# Reads:  outputs/tom_validation/tom_errors.csv
# Writes: outputs/tom_validation/clmm_results.json
#
# Usage: Rscript clmm_analysis.R [path_to_tom_errors.csv] [output_json]

suppressPackageStartupMessages({
  library(ordinal)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
input_csv  <- if (length(args) >= 1) args[1] else "outputs/tom_validation/tom_errors.csv"
output_json <- if (length(args) >= 2) args[2] else "outputs/tom_validation/clmm_results.json"

cat(sprintf("Loading: %s\n", input_csv))
df <- read.csv(input_csv, stringsAsFactors = FALSE)
cat(sprintf("  N = %d errors\n", nrow(df)))

# Prepare variables
df$detection_count_ord <- factor(df$detection_count, levels = c(1, 2, 3), ordered = TRUE)
df$tom_linear   <- as.numeric(df$tom_level)
df$is_major     <- as.integer(df$severity == "Major")
df$seg_len_z    <- scale(df$segment_length)[, 1]
df$sys_qual_z   <- scale(df$system_quality)[, 1]
df$system       <- as.factor(df$system)
df$doc          <- as.factor(df$doc)

# ── Full model with crossed random effects ──────────────────────────
cat("Fitting full CLMM (this may take a few minutes)...\n")
t0 <- Sys.time()

full_model <- tryCatch({
  clmm(
    detection_count_ord ~ tom_linear + is_major + seg_len_z + sys_qual_z +
      (1 | system) + (1 | doc),
    data = df, link = "logit",
    control = clmm.control(maxIter = 200, gradTol = 1e-4)
  )
}, error = function(e) {
  cat(sprintf("  Full model failed: %s\n", e$message))
  cat("  Falling back to system-only random effect...\n")
  clmm(
    detection_count_ord ~ tom_linear + is_major + seg_len_z + sys_qual_z +
      (1 | system),
    data = df, link = "logit"
  )
})

cat(sprintf("  Full model fit: %.1f seconds\n", as.numeric(Sys.time() - t0, units = "secs")))

# ── Reduced model (no ToM) for LR test ──────────────────────────────
cat("Fitting reduced CLMM (no ToM)...\n")
reduced_model <- tryCatch({
  clmm(
    detection_count_ord ~ is_major + seg_len_z + sys_qual_z +
      (1 | system) + (1 | doc),
    data = df, link = "logit",
    control = clmm.control(maxIter = 200, gradTol = 1e-4)
  )
}, error = function(e) {
  clmm(
    detection_count_ord ~ is_major + seg_len_z + sys_qual_z +
      (1 | system),
    data = df, link = "logit"
  )
})

# Likelihood ratio test
lr_stat <- 2 * (as.numeric(logLik(full_model)) - as.numeric(logLik(reduced_model)))
lr_df   <- length(coef(full_model)) - length(coef(reduced_model))
lr_p    <- 1 - pchisq(lr_stat, lr_df)

# ── Extract coefficients ────────────────────────────────────────────
summ <- summary(full_model)
fixed_coefs <- summ$coefficients

# Build coefficient list (skip threshold parameters)
coef_names <- c("tom_linear", "is_major", "seg_len_z", "sys_qual_z")
coefs <- list()
for (nm in coef_names) {
  if (nm %in% rownames(fixed_coefs)) {
    coefs[[nm]] <- list(
      coef = round(fixed_coefs[nm, "Estimate"], 4),
      se   = round(fixed_coefs[nm, "Std. Error"], 4),
      z    = round(fixed_coefs[nm, "z value"], 4),
      p    = round(fixed_coefs[nm, "Pr(>|z|)"], 6)
    )
  }
}

# Random effects variance components
ranef_vars <- as.data.frame(VarCorr(full_model))
random_effects <- list()
for (i in seq_len(nrow(ranef_vars))) {
  random_effects[[ranef_vars$grp[i]]] <- list(
    variance = round(ranef_vars$vcov[i], 6),
    std_dev  = round(ranef_vars$sdcor[i], 6)
  )
}

# 95% CI for ToM linear coefficient
tom_coef_val <- fixed_coefs["tom_linear", "Estimate"]
tom_se_val   <- fixed_coefs["tom_linear", "Std. Error"]
ci_lo <- tom_coef_val - 1.96 * tom_se_val
ci_hi <- tom_coef_val + 1.96 * tom_se_val

# ── Assemble results ────────────────────────────────────────────────
result <- list(
  experiment = "V3_CLMM_R",
  model = "Cumulative link mixed model (clmm)",
  formula = deparse(formula(full_model)),
  n = nrow(df),
  log_likelihood = round(as.numeric(logLik(full_model)), 2),
  aic = round(AIC(full_model), 2),
  bic = round(BIC(full_model), 2),
  coefficients = coefs,
  tom_linear_95ci = c(round(ci_lo, 4), round(ci_hi, 4)),
  random_effects = random_effects,
  lr_test = list(
    chi2    = round(lr_stat, 4),
    df      = lr_df,
    p_value = round(lr_p, 6),
    significant = lr_p < 0.05,
    full_loglik    = round(as.numeric(logLik(full_model)), 2),
    reduced_loglik = round(as.numeric(logLik(reduced_model)), 2)
  ),
  R_version = R.version.string,
  ordinal_version = as.character(packageVersion("ordinal"))
)

tom_p <- coefs$tom_linear$p
tom_b <- coefs$tom_linear$coef
if (!is.null(tom_p) && tom_p < 0.05) {
  direction <- if (tom_b < 0) "negative" else "positive"
  result$interpretation <- sprintf(
    "SIGNIFICANT: ToM level has a %s effect on detection count (b=%.4f, 95%% CI [%.4f, %.4f], p<.001). LR test: chi2=%.2f (df=%d), p=%.6f.",
    direction, tom_b, ci_lo, ci_hi, lr_stat, lr_df, lr_p
  )
} else {
  result$interpretation <- sprintf(
    "NOT SIGNIFICANT: ToM effect b=%.4f, p=%s.", tom_b, format(tom_p)
  )
}

# Write JSON
write(toJSON(result, auto_unbox = TRUE, pretty = TRUE, na = "null"), output_json)
cat(sprintf("\nResults written to: %s\n", output_json))
cat(sprintf("\n%s\n", result$interpretation))
