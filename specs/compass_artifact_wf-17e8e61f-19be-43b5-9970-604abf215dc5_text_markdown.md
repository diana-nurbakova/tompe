# Adapting AI evaluation tools to machine translation education: a comprehensive research landscape

**No existing platform combines controlled error injection, scaffolded post-editing training, and MT quality evaluation in a single pedagogical environment** — making this the most significant gap at the intersection of educational technology and translation studies. The IILAP model of generating controlled assessment items with known errors for critical AI evaluation has no analog in translator training, despite mature error taxonomies (MQM), advancing quality estimation models (xCOMET, GEMBA-MQM), and growing evidence that NMT's fluency actively undermines students' error detection abilities. The infrastructure to build such a tool now exists across adjacent fields, but nobody has assembled the pieces.

This report synthesizes research across seven domains — existing training platforms, error taxonomies, error injection methods, pedagogical frameworks, cognitive research, quality estimation technology, and gap analysis — to map the landscape for building an IILAP-inspired MT evaluation training tool.

---

## Existing tools solve fragments of the problem but none solve it whole

The current landscape of computer-assisted translation education (CATE) tools reveals a fragmented ecosystem where professional tools are repurposed for education and academic prototypes remain narrow in scope.

**PET** (Post-Editing Tool), developed by Aziz, Castilho, and Specia at the University of Wolverhampton (2012), remains the most widely used research-oriented PE tool. It logs keystrokes, timing, and edit operations, calculates HTER between draft and post-edited versions, and supports quality assessment tags — but contains **zero pedagogical scaffolding**, no error taxonomy, and no feedback mechanism. It is a data collection instrument, not a training platform.

The **ACCEPT Academic Portal** (University of Geneva, EU FP7, 2012–2015) represents the most integrated educational workflow found, uniquely combining pre-editing, MT, post-editing, and evaluation in a single pedagogical pipeline. Developed by Bouillon, Gerlach, and colleagues at the Faculty of Translation and Interpreting, it allowed students to compare pre-edited and raw source translations side-by-side. However, it relied on Moses phrase-based SMT — now technologically obsolete — and offered no adaptive difficulty or error injection.

**MateCat** (FBK, EU FP7) and **Memsource/Phrase** serve as professional CAT tools adopted by universities. Herget's 2021 classroom experiment with MateCat at the University of Aveiro revealed that **30% of students were influenced by MT suggestions against target language conventions**, and students found error categorization challenging — precisely the skills a controlled training environment should develop. These tools track productivity metrics but provide no pedagogical feedback loop.

The most promising recent development is **postedit.me** and its accompanying **MTPEAS** (Machine Translation Post-Editing Annotation System), developed by Lefer, Bodart, Piette, and Obrusník at UCLouvain (2021–2024). MTPEAS introduces a seven-category taxonomy purpose-built for evaluating student PE work: value-adding edits, successful edits, unnecessary edits, incomplete edits, error-introducing edits, unsuccessful edits, and missing edits. Combined with TAS (Translation-oriented Annotation System) for linguistic error dimensions, this represents the **most sophisticated pedagogical error framework** in the field. The postedit.me app computes TER and expansion rates and provides structured feedback — but it still requires manual lecturer annotation and uses real MT output rather than controlled items with injected errors.

The **MultiTraiNMT** project (Erasmus+, 2019–2022), led by Universitat Autònoma de Barcelona with Dublin City University, Université Grenoble-Alpes, and Universitat d'Alacant, produced the open-access coursebook "Machine Translation for Everyone" (Language Science Press, 2022) with over 250 activities and **MutNMT**, a pedagogical NMT interface built on JoeyNMT. MutNMT lets students train their own engines, inspect outputs, and compare systems — addressing MT-as-black-box concerns — but does not target error identification or quality evaluation skills directly.

**SDL Trados/RWS** and **Phrase** offer certification programs that provide some progression through levels, but these test tool proficiency rather than PE competence itself.

---

## MQM Core emerges as the optimal error taxonomy for controlled assessment

Among the error classification systems surveyed, the **Multidimensional Quality Metrics (MQM)** framework — developed under the EU-funded QTLaunchPad project (2012–2014) by Lommel, Burchardt, and Uszkoreit at DFKI — stands out as the most suitable foundation for an IILAP-style controlled assessment tool. The full MQM hierarchy spans **eight top-level dimensions** (Accuracy, Fluency, Terminology, Locale Convention, Style, Verity, Design, Internationalization) with over 100 specific issue types, three severity levels (Minor = 1, Major = 5, Critical = 25), and a formal scoring formula.

The **MQM Core** subset, comprising approximately 20 common issue types, offers the best balance of granularity and pedagogical usability. A study by Koby, Melby, and Lommel demonstrated the "viability of using the MQM framework by novice raters to judge translations," using 29 student translations rated by 9 novice and 2 expert raters with Many-Facet Rasch Measurement for reliability. Since 2021, MQM has served as the official evaluation framework for the WMT shared tasks, replacing Direct Assessment — giving it both academic rigor and industry currency.

The **MQM-DQF harmonization** (completed under QT21, announced June 2015) unified MQM with TAUS's industry-standard Dynamic Quality Framework, ensuring any DQF metric maps directly to the MQM hierarchy. This dual alignment means students trained on MQM-based assessment transfer seamlessly to both academic and professional contexts.

For a controlled assessment tool, MQM's structure enables precise error injection because each error type has a clear definition, severity mapping, and scoring weight. **Error types map cleanly to injectable perturbations**: an Accuracy/Mistranslation error can be injected by substituting a semantically incorrect translation; a Fluency/Grammar error by introducing a morphological disagreement; a Terminology error by replacing a domain-specific term with a general synonym. The severity system provides natural difficulty scaffolding — Minor errors (subtle register shifts) are harder to detect than Critical errors (complete meaning distortion).

Alternative taxonomies serve complementary roles. **Vilar et al.'s 2006 typology** (5 categories: Missing Words, Word Order, Incorrect Words, Unknown Words, Punctuation) is compact enough for introductory courses. The **SCATE taxonomy** (Tezcan, Hoste, and Macken, 2017) adds alignment-based inter-annotator agreement methods useful for corpus annotation exercises. The **ATA error framework** uses an exponential severity scale (0–16 points per error) suited to certification contexts but too coarse for fine-grained training. **MTPEAS** uniquely evaluates the quality of the post-editing process itself rather than the translation product, making it complementary to MQM-based error identification.

---

## Error injection for MT training is an unoccupied research space

**No system has been built that deliberately injects controlled, categorized errors into MT output for the purpose of training translation students.** This finding, consistent across all research streams, represents the single most significant gap identified. However, adjacent fields provide a rich toolkit of techniques that could be adapted.

**Tagged corruption models** offer the most directly applicable approach. Stahlberg and Kumar (2021) demonstrated that ERRANT error type tags can guide synthetic error generation: given a clean sentence and an error type tag, models produce ungrammatical sentences of the specified type. Controlling error tag frequency distributions allows calibrating the error profile to match any target distribution — precisely the mechanism needed for difficulty-controlled assessment items.

**GenERRate** (Foster and Andersen, 2009, Dublin City University) is an open-source tool that automatically inserts errors into text by moving, substituting, inserting, and removing words using POS tags for more realistic errors. Originally designed for grammatical error detection research, its architecture could be adapted for translation error injection. Controllable error synthesis by Wang et al. (2020) demonstrated that fixing corruption probability at 40% with consistent error type ratios optimizes downstream model performance — suggesting principled approaches to calibrating error density.

**Round-trip translation** provides a low-cost error generation method. Lichtarge et al. (2019, NAACL) showed that translating English to German and back creates naturally noisy counterparts. Kementchedjhieva and Søgaard (2023, EACL) re-evaluated this across five languages, confirming consistent error generation. The errors produced are authentic MT artifacts — word order distortions, lexical substitutions, omission of nuance — but their types and severity are **not controllable**, limiting their utility for scaffolded assessment.

**Adversarial MT attacks** could be repurposed pedagogically. Belinkov and Bisk (2018, ICLR) systematically demonstrated that synthetic noise (character swaps, mid-word replacements, keyboard-adjacency errors) breaks NMT models in predictable ways. Zhang et al.'s WSLS attack (ACL 2021) makes minor source modifications causing dramatic translation degradation. TransFool (Sadrizadeh et al., 2023, ICLR) generates fluent adversarial examples degrading translation quality for over 60% of sentences. These methods could generate controlled source perturbations that produce predictable MT degradation patterns for training exercises.

**Noise injection techniques** from data augmentation research provide additional mechanisms. Khayrallah and Koehn (2018, EMNLP) categorized five noise types and their effects on NMT: misaligned sentences, wrong source language, untranslated source copied to target, short segments, and wrong target language. Edunov et al. (2018) showed that adding word deletion, replacement with blank tokens, and word permutation to back-translated data creates a controlled noise profile.

The most promising approach for an IILAP-inspired tool would combine **LLM-based error generation with MQM-guided injection**. Recent work on GEMBA-MQM (Kocmi and Federmann, 2023) and InstructScore (Xu et al., 2023) shows that LLMs can reliably detect and categorize MT errors along MQM dimensions. Reversing this pipeline — prompting an LLM to introduce specific MQM-categorized errors into clean translations at controlled severity and density levels — is technically feasible but has not been attempted. Ki and Carpuat (2024) demonstrated that LLaMA-2 can effectively use MQM error annotations to guide post-editing, suggesting the reverse operation (using annotations to guide error introduction) is within reach.

---

## Pedagogical frameworks converge on a staged competence model

The theoretical foundations for MT post-editing pedagogy are well-established, though their operationalization in software remains incomplete.

**O'Brien's 2002 proposal** — the first formal PE curriculum — identified skills including general MT knowledge, terminology management, text-linguistic competence, and critically, a **positive attitude toward MT**. This attitudinal dimension has been echoed by every subsequent framework. O'Brien established that PE involves cognitive processes distinct from both human translation and revision.

The **PACTE translation competence model** (Hurtado Albir et al., 2003–2017, Universitat Autònoma de Barcelona) provides the dominant theoretical architecture. Its five sub-competences — bilingual, extra-linguistic, knowledge about translation, instrumental, and strategic — have been adapted to PE by Robert, Schrijver, and Ureel (2023–2024, UCLouvain/Antwerp), who explicitly investigated how post-editing competence (PEC) differs from translation competence (TC) and revision competence (TRC). Their critical finding: **PE competence is not a subset of translation competence.** Yamada's 2014 study provides supporting evidence — students with good translation grades were "not always qualified post-editors," and only a loose correlation existed between general translation competence and PE performance.

The **EMT Competence Framework (2022)** now explicitly includes PE as Skill #14: "Post-edit MT output using style guides and terminology glossaries to maintain quality standards in MT-enhanced translation projects." However, Froeliger et al. (2022) criticized the revision as a "missed opportunity" to develop PE-specific competences more fully.

Rico and Torrejón's 2012 framework identified three skill dimensions for PE: core psycho-physiological competencies (managing uncertainty, controlling editing norms), linguistic skills (error identification and correction), and instrumental competence (MT systems, CAT tools, terminology databases). Koponen's 2015 course at the University of Helsinki demonstrated that **students need to understand why MT makes certain errors, not just how to fix them** — a pedagogical insight directly supporting the case for controlled error exposure.

Synthesizing these frameworks, an evidence-based **staged progression model** for an assessment tool emerges:

- **Stage 1 (Detection)**: Identifying obvious errors — untranslated words, severe mistranslations, grammatical breakdowns. Aligns with MQM Critical severity. Equivalent to information literacy "navigation."
- **Stage 2 (Classification)**: Categorizing errors by type (accuracy vs. fluency vs. terminology) and severity. Builds taxonomic knowledge using MQM Core categories.
- **Stage 3 (Correction)**: Performing targeted post-edits that address identified errors without introducing new ones or making unnecessary changes. Distinguishes light from full PE.
- **Stage 4 (Evaluation)**: Assessing overall translation quality, determining whether PE is worthwhile versus retranslation, and providing structured quality reports. Equivalent to information literacy "editing."

---

## NMT fluency creates a cognitive trap that controlled training could address

The cognitive research on post-editing reveals a paradox central to the proposed tool's rationale: **higher MT quality makes error detection harder, not easier.** This "automation bias" finding makes the case for controlled error exposure training particularly compelling.

Krings's 2001 tripartite effort model — temporal effort (speed), technical effort (keystrokes/edits), and cognitive effort (mental processing) — remains the dominant framework. Eye-tracking research by Carl, Schaeffer, and colleagues at CRITT (Copenhagen Business School) established that PE is fundamentally **target-text-oriented**: fixations during PE occur more frequently on the target text than in human translation. This target-focus means post-editors may not adequately consult the source text, missing faithfulness errors masked by fluent target prose.

Yamada's 2019 study comparing Google SMT (2014) and Google NMT (2019) post-editing by students provides the starkest evidence. NMT produced fewer total errors (37% major errors vs. 72% for SMT), but **students exhibited a poorer error correction rate with NMT** despite reporting similar perceived cognitive effort. NMT produces "human-like errors" that are intrinsically harder for students to detect — a form of **error blindness** that current PE training does not systematically address.

Daems, Vandepitte, Hartsuiker, and Macken's 2017 work (Frontiers in Psychology) found that students required **significantly more time in pauses** than professional translators, an effect that outweighed MT quality differences. Different MT error types predicted different effort indicators: accuracy errors demanded different cognitive resources than fluency errors. This finding directly supports designing assessment items that target specific error types to develop specific detection skills.

Metacognitive regulation has emerged as a significant predictor of PE performance. Li's 2024 dissertation (University of North Texas) found a **statistically significant relationship** between metacognitive regulation and MTPE performance. Hu, Zheng, and Wang (2020, The Interpreter and Translator Trainer) developed a Metacognitive Self-Regulation Inventory (MSRI) for translator self-training that effectively transformed declarative knowledge into procedural knowledge through repeated practice with planning, monitoring, and evaluation strategies. Yang and Wang (2023) found self-regulation had a direct positive influence on MTPE performance (β = .48). A controlled assessment tool with scaffolded progression could systematically develop these metacognitive skills — making error detection strategies explicit rather than leaving them to develop incidentally.

The novice-expert divide manifests differently than expected. Stasimioti and Sosoni (2021) found experienced translators tend to **overcorrect** NMT output (performing unnecessary edits), while novices' more positive attitudes toward MT don't reduce their effort. A 2024 study on Turkish legal texts found experienced translators exerted **higher** cognitive, temporal, and technical effort — suggesting experts apply more thorough quality standards. The implication for tool design: training should address both under-editing (novice automation bias) and over-editing (unnecessary changes that waste effort), with controlled items that include both real errors and "clean" segments that should not be edited.

---

## Quality estimation models could power the scaffolding layer

Automated MT quality estimation has advanced to the point where it could serve as either a ground truth generator or a scaffolding mechanism in a pedagogical tool, analogous to NLI-based verification in IILAP.

**xCOMET** (Guerreiro et al., 2024, TACL) represents the breakthrough model for pedagogical applications. It integrates both sentence-level regression and **word-level error span detection** through dual prediction heads, categorizing spans as minor, major, or critical errors aligned with MQM. Available in 3.5B parameter (XL) and 10.7B parameter (XXL) versions, xCOMET achieves state-of-the-art performance across all evaluation types. When combined with **xTower**, it generates natural language explanations of each detected error span — an ideal mechanism for automated student feedback.

**GEMBA-MQM** (Kocmi and Federmann, WMT 2023) uses fixed 3-shot GPT-4 prompting to produce MQM error span annotations with severity-weighted error counts. Its reference-free, language-agnostic design makes it particularly suitable for a language-pair-agnostic assessment tool. The ESAAI protocol (2024) showed that combining GEMBA pre-annotations with human review achieves equal reliability to pure human annotation while detecting **3x more error spans** — suggesting a hybrid pipeline for generating high-quality assessment ground truth.

The **QE4PE study** (Sarti et al., 2025, TACL) provides the most direct evidence for pedagogical QE use. Testing 42 professional post-editors, it found that QE highlights (both human-generated and automated) **provide meaningful scaffolding** for post-editing, though effectiveness varied by domain, language pair, and editor speed. Word-level QE proved most pedagogically valuable because it highlights specific error locations, creating teachable moments.

For a controlled assessment tool, the optimal pipeline would be: (1) use xCOMET-XL to generate candidate error spans as initial ground truth; (2) supplement with GEMBA-MQM annotations for error categorization; (3) have expert annotators validate using the ESAAI protocol; (4) use validated annotations as the definitive answer key. For error injection, the pipeline reverses: inject known errors into clean translations, verify QE models detect them, and deploy verified items as assessment materials.

However, important limitations remain. Sentence-level QE shows only moderate correlation with human MQM scores (Pearson ~0.4–0.6 depending on language pair). Word-level QE still has "modest agreement with human annotations" at the segment level. All QE models perform better at system-level ranking than segment-level evaluation — meaning they work better for calibrating overall difficulty levels than for precise individual error detection. These limitations reinforce the need for human expert validation in the assessment item creation pipeline.

---

## The critical gap: no controlled assessment environment bridges these mature components

The gap analysis reveals that while each component needed for an IILAP-inspired MT evaluation tool exists in some form, **nobody has assembled them**. This absence is striking given the maturity of the individual components.

The landscape has mature error taxonomies (MQM, with over a decade of refinement and WMT standardization), advancing QE models capable of word-level error detection and categorization (xCOMET, GEMBA-MQM), well-documented pedagogical frameworks with staged competence models (PACTE adapted to PE, O'Brien, Koponen), robust evidence that NMT fluency creates automation bias requiring systematic training to overcome (Yamada 2019, Daems et al. 2017), and working error injection techniques from adjacent NLP fields (tagged corruption models, GenERRate, adversarial examples). Yet no tool combines even two of these elements in a controlled pedagogical environment.

The most critical gaps, ranked by severity:

- **No controlled item generation for translation assessment.** While information literacy has IILAP and language testing has established item generation frameworks, MT evaluation training relies exclusively on authentic MT output with uncontrolled error distributions. This means teachers cannot target specific error types, calibrate difficulty, or ensure comprehensive coverage of the error taxonomy.
- **No scaffolded progression in any MT training software.** Progression exists only at the course design level (instructor decisions about assignment sequencing), not embedded in technology. No tool automatically adjusts from obvious to subtle errors based on student performance.
- **No dual-mode tool for PE and quality evaluation.** postedit.me comes closest by supporting both PE practice and quality evaluation of PE output, but operates on authentic rather than controlled MT output. The ACCEPT portal combined pre-editing, MT, PE, and evaluation but is technologically obsolete.
- **No crossover between information literacy assessment and translation education.** Zhang and Qian's 2021 paper on "Technology Infused Learning: Developing Information Literacy in Translator Training" is nearly alone in bridging these fields. The IILAP model of controlled chatbot interactions with known errors and structured analytics has no parallel in translation tools.
- **No formal framework mapping MT evaluation skills to a progression model analogous to CCL's "navigator to editor."** The Dreyfus model and PACTE describe general competence development, but no translation-specific framework operationalizes skill stages in a way that could drive item selection algorithms.

Recent developments (2023–2026) add urgency to this gap. LLMs have made translation accessible to non-translators, intensifying the need for critical MT evaluation skills. Zhang, Zhao, and Doherty (2025, The Interpreter and Translator Trainer) found students have "more confidence in their competence to identify and correct errors produced by AI tools" than is warranted — an overconfidence that controlled assessment could calibrate. Bowker's Machine Translation Literacy initiative (University of Ottawa) and Krüger's 2024 five-dimensional AI literacy framework for translators provide conceptual grounding, but neither has produced assessment tools.

---

## Conclusion: assembling the pieces for a new kind of tool

The research landscape reveals that building an IILAP-inspired MT evaluation training tool is not a speculative proposition but an engineering and design challenge. Every major component exists: **MQM Core** provides the error taxonomy with 20 well-defined types, three severity levels, and proven viability with novice raters; **tagged corruption models and LLM-based error generation** provide the injection mechanism; **xCOMET and GEMBA-MQM** provide automated error detection for ground truth validation and scaffolding; **MTPEAS** provides the PE quality evaluation framework; and **metacognitive self-regulation research** provides the pedagogical theory for skill progression.

Three design principles emerge from the evidence. First, the tool must address **automation bias explicitly** — including clean segments alongside error-laden ones, so students learn to resist both under-editing (accepting MT errors) and over-editing (making unnecessary changes). Second, **error type should drive difficulty scaffolding**: surface-level fluency errors (spelling, grammar) are detectable by beginners, while semantic accuracy errors (subtle mistranslation, omission of nuance) and pragmatic errors (register, cultural reference) require advanced skills. Third, the tool should operate in **dual mode** — quality evaluation (identify and classify errors using MQM) and post-editing (correct errors efficiently) — because Yamada's and Robert et al.'s findings demonstrate these are related but distinct competences.

The French-English language pair is an ideal starting point given the extensive MQM-annotated data available from WMT shared tasks, the SCATE corpus resources, and the strong representation of French in EU-funded MT projects. The MQM-based architecture ensures language-agnostic design: error types are defined at the linguistic level (accuracy, fluency, terminology) rather than the language-specific level, and QE models like xCOMET and CometKiwi operate across language pairs without retraining.

What remains missing is the **integration work** — the controlled item generation pipeline, the adaptive difficulty algorithm, the dual-mode interface, and the analytics dashboard that transforms interaction logs into pedagogical insights. This is precisely the contribution space that an IILAP-inspired tool could fill, creating the first controlled assessment environment for MT evaluation skills that translation education has lacked while information literacy has had for years.