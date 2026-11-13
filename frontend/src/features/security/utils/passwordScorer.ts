import { ZxcvbnFactory } from '@zxcvbn-ts/core'
import * as zxcvbnCommon from '@zxcvbn-ts/language-common'
import * as zxcvbnEn from '@zxcvbn-ts/language-en'

/**
 * Builds the zxcvbn scorer with the common and English dictionaries. Imported
 * only lazily, so zxcvbn ships in one chunk named after this module, which the
 * service worker leaves out of its precache (see `vite.config.ts`).
 *
 * @returns The configured scorer.
 */
export function createPasswordScorer(): ZxcvbnFactory {
  return new ZxcvbnFactory({
    dictionary: { ...zxcvbnCommon.dictionary, ...zxcvbnEn.dictionary },
    graphs: zxcvbnCommon.adjacencyGraphs,
    translations: zxcvbnEn.translations,
  })
}
