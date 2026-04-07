#!/usr/bin/env Rscript
# §5.5 — Logistic GLMM with random slopes per rater for V4.
#
# Fits a binary GLMM:
#   detected ~ tom_level + severity + segment_length +
#              (1 + tom_level | rater) + (1 | system) + (1 | segment)
#
# Tests H3: random slopes for ToM by rater are significant.
#
# Reads:  outputs/tom_validation/rater_level_data.csv
# Writes: outputs/tom_validation/glmm_results.json
#
# Usage: Rscript rater_glmm.R [path_to_rater_data.csv] [output_json]

suppressPackageStartupMessages({
  library(lme4)
  library(jsonlite)
})

args <- commandArgs(trailingOnly = TRUE)
input_csv  <- if (length(args) >= 1) args[1] else "outputs/tom_validation/rater_level_data.csv"
output_json <- if (length(args) >= 2) args[2] else "outputs/tom_validation/glmm_results.json"

cat(sprintf("Loading: %s\n", input_csv))
df <- read.csv(input_csv, stringsAsFactors = FALSE)
cat(sprintf("  N = %d observations, %d unique raters\n",
            nrow(df), length(unique(df$rater))))

# Prepare variables
df$is_major     <- as.integer(df$severity == "Major")
df$seg_len_z    <- scale(df$segment_length)[, 1]
df$rater        <- as.factor(df$rater)
df$system       <- as.factor(df$system)
df$segment_id   <- as.factor(df$segment_id)
df$tom_level    <- as.numeric(df$tom_level)

# ── Full model: random intercept + slope for ToM by rater ──────────
cat("Fitting full GLMM with random slopes (this may take several minutes)...\n")
t0 <- Sys.time()

full_model <- tryCatch({
  glmer(
    detected ~ tom_level + is_major + seg_len_z +
      (1 + tom_level | rater) + (1 | system),
    data = df, family = binomial,
    control = glmerControl(optimizer = "bobyqa", optCtrl = list(maxfun = 100000))
  )
}, error = function(e) {
  cat(sprintf("  Full model failed: %s\n", e$message))
  cat("  Falling back to random intercept only by rater...\n")
  glmer(
    detected ~ tom_level + is_major + seg_len_z +
      (1 | rater) + (1 | system),
    data = df, family = binomial,
    control = glmerControl(optimizer = "bobyqa")
  )
})

cat(sprintf("  Full model fit: %.1f seconds\n", as.numeric(Sys.time() - t0, units = "secs")))

# ── Reduced model: random intercept only ───────────────────────────
cat("Fitting reduced GLMM (random intercept only)...\n")
reduced_model <- tryCatch({
  glmer(
    detected ~ tom_level + is_major + seg_len_z +
      (1 | rater) + (1 | system),
    data = df, family = binomial,
    control = glmerControl(optimizer = "bobyqa")
  )
}, error = function(e) NULL)

# LR test for random slopes (H3)
lr_test <- list(skipped = TRUE, reason = "Reduced model failed")
if (!is.null(reduced_model)) {
  lr_stat <- 2 * (as.numeric(logLik(full_model)) - as.numeric(logLik(reduced_model)))
  lr_df <- attr(logLik(full_model), "df") - attr(logLik(reduced_model), "df")
  # For variance components on the boundary, use mixture chi-square (50:50)
  lr_p_naive <- 1 - pchisq(lr_stat, max(lr_df, 1))
  lr_p_mixture <- 0.5 * (1 - pchisq(lr_stat, max(lr_df - 1, 1))) +
                  0.5 * (1 - pchisq(lr_stat, max(lr_df, 1)))

  lr_test <- list(
    chi2 = round(lr_stat, 4),
    df = lr_df,
    p_value_naive = round(lr_p_naive, 6),
    p_value_mixture = round(lr_p_mixture, 6),
    significant = lr_p_mixture < 0.05,
    note = "p_value_mixture uses 50:50 chi-square mixture for boundary variance test"
  )
}

# ── Extract fixed effects ──────────────────────────────────────────
fixed_coefs <- summary(full_model)$coefficients
fixed_effects <- list()
for (nm in rownames(fixed_coefs)) {
  fixed_effects[[nm]] <- list(
    coef = round(fixed_coefs[nm, "Estimate"], 4),
    se   = round(fixed_coefs[nm, "Std. Error"], 4),
    z    = round(fixed_coefs[nm, "z value"], 4),
    p    = round(fixed_coefs[nm, "Pr(>|z|)"], 6)
  )
}

# Random effects variance components
ranef_summary <- as.data.frame(VarCorr(full_model))
random_effects_list <- list()
for (i in seq_len(nrow(ranef_summary))) {
  key <- if (is.na(ranef_summary$var2[i])) {
    paste(ranef_summary$grp[i], ranef_summary$var1[i], sep = "_")
  } else {
    paste(ranef_summary$grp[i], ranef_summary$var1[i], ranef_summary$var2[i], sep = "_")
  }
  random_effects_list[[key]] <- list(
    variance = round(ranef_summary$vcov[i], 6),
    std_dev  = round(ranef_summary$sdcor[i], 6)
  )
}

# Per-rater BLUPs (best linear unbiased predictors) for ToM slopes
rater_ranef <- ranef(full_model)$rater
rater_slopes <- list()
fixed_tom_coef <- fixed_coefs["tom_level", "Estimate"]
if ("tom_level" %in% colnames(rater_ranef)) {
  for (r in rownames(rater_ranef)) {
    rater_slopes[[r]] <- round(fixed_tom_coef + rater_ranef[r, "tom_level"], 4)
  }
} else {
  for (r in rownames(rater_ranef)) {
    rater_slopes[[r]] <- round(fixed_tom_coef, 4)
  }
}

# ── Assemble results ────────────────────────────────────────────────
result <- list(
  experiment = "V4_GLMM_R",
  model = "Logistic GLMM with random slopes",
  formula = deparse(formula(full_model)),
  n_observations = nrow(df),
  n_raters = length(unique(df$rater)),
  log_likelihood = round(as.numeric(logLik(full_model)), 2),
  aic = round(AIC(full_model), 2),
  bic = round(BIC(full_model), 2),
  fixed_effects = fixed_effects,
  random_effects = random_effects_list,
  rater_tom_slopes = rater_slopes,
  random_slope_lr_test = lr_test,
  R_version = R.version.string,
  lme4_version = as.character(packageVersion("lme4"))
)

if (!is.null(lr_test$significant) && lr_test$significant) {
  slopes_vec <- unlist(rater_slopes)
  result$interpretation <- sprintf(
    "H3 SUPPORTED: Significant random slopes for ToM by rater (chi2=%.2f, p=%.4f). Slopes range: %.4f to %.4f.",
    lr_test$chi2, lr_test$p_value_mixture, min(slopes_vec), max(slopes_vec)
  )
} else if (!is.null(lr_test$chi2)) {
  result$interpretation <- sprintf(
    "H3 NOT SUPPORTED: No significant random slopes (chi2=%.2f, p=%.4f).",
    lr_test$chi2, lr_test$p_value_mixture
  )
} else {
  result$interpretation <- "H3 inconclusive: LR test could not be computed."
}

# Write JSON
write(toJSON(result, auto_unbox = TRUE, pretty = TRUE, na = "null"), output_json)
cat(sprintf("\nResults written to: %s\n", output_json))
cat(sprintf("\n%s\n", result$interpretation))
